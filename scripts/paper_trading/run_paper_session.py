"""CLI paper trading — Cale B, dry_run obligatoriu."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import signal
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.kraken import KrakenPublicOHLCSource
from src.data.sources import CsvBarDataSource, timeframe_delta
from src.audit.postgres_store import open_audit_log
from src.engine.cost_models import BASE_SPREAD_BPS
from src.engine.adapters.kraken_paper import (
    assert_no_kraken_trading_keys,
    build_paper_node_config,
)
from src.engine.llm_client import LLMProposalClient
from src.engine.paper_config import load_paper_trading_config
from src.engine.portfolio_tracker import PortfolioTracker
from src.engine.proposal_types import ParsedProposal, ProposalContext, RejectedProposal
from src.engine.strategy_paper import PaperTradingLoop
from src.execution.broker import SimulatedBroker
from src.execution.human_approval import ApprovalGate, ScriptedApprovalOperator
from src.execution.order_gateway import OrderGateway
from src.execution.reconciliation import Reconciliation
from src.execution.repository import open_idempotency_store, open_portfolio_store
from src.monitor.heartbeat import Heartbeat
from src.monitor.watchdog import Watchdog
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.config_schema import load_risk_limits
from src.risk.kill_switch import KillSwitch
from src.risk.portfolio_state import load_instrument_rules
from src.risk.risk_engine import RiskEngine


class BaselineProposalClient:
    """Client determinist: EMA-cross, fără LLM. Folosit când --skip-llm."""

    def __init__(self, *, fast_period: int, slow_period: int) -> None:
        self._fast = fast_period
        self._slow = slow_period
        self._history: list = []

    def request_proposal(
        self,
        context: ProposalContext,
        timeout_s: float | None = None,  # noqa: ARG002
    ) -> ParsedProposal | RejectedProposal:
        from src.data.sources import Bar
        from decimal import Decimal

        # Context-only client: reproduce direction from market_summary tokens.
        # If EMA isn't ready the baseline helper returns None → avoid.
        dummy = Bar(
            instrument=context.instrument,
            timestamp=context.as_of,
            open=Decimal("1"),
            high=Decimal("1"),
            low=Decimal("1"),
            close=Decimal("1"),
            volume=Decimal("1"),
        )
        self._history.append(dummy)
        if "ema_fast=na" in context.market_summary or "ema_slow=na" in context.market_summary:
            return ParsedProposal(
                instrument=context.instrument,
                direction="avoid",
                confidence=1.0,
                rationale="baseline_indicators_not_ready",
            )
        if "ema_fast=" in context.market_summary and "ema_slow=" in context.market_summary:
            # Parse numeric ema values from the summary produced by proposal_context_at.
            parts = dict(
                item.split("=", 1)
                for item in context.market_summary.split()
                if "=" in item
            )
            try:
                fast = float(parts.get("ema_fast", "nan"))
                slow = float(parts.get("ema_slow", "nan"))
            except ValueError:
                return ParsedProposal(
                    instrument=context.instrument,
                    direction="avoid",
                    confidence=1.0,
                    rationale="baseline_parse_failed",
                )
            direction = "long" if fast >= slow else "exit"
            return ParsedProposal(
                instrument=context.instrument,
                direction=direction,  # type: ignore[arg-type]
                confidence=1.0,
                rationale="baseline_ema_cross_from_context",
            )
        return ParsedProposal(
            instrument=context.instrument,
            direction="avoid",
            confidence=1.0,
            rationale="baseline_no_signal",
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Faza 5 paper trading (Path B, dry_run)")
    parser.add_argument("--config", default=str(REPO_ROOT / "config" / "paper_trading.yaml"))
    parser.add_argument("--csv", default="", help="Local bars CSV (replay, zero network)")
    parser.add_argument("--llm-url", default="http://127.0.0.1:8765")
    parser.add_argument("--skip-llm", action="store_true")
    parser.add_argument(
        "--operator",
        choices=("scripted", "file"),
        default="scripted",
        help="scripted writes the same decision file a human would; file waits on disk",
    )
    parser.add_argument("--runtime-dir", default="")
    parser.add_argument("--max-sessions", type=int, default=0)
    parser.add_argument(
        "--mode",
        choices=("batch", "stream"),
        default="batch",
        help="batch = historical window then exit; stream = poll closed bars until stop",
    )
    parser.add_argument("--poll-interval-s", type=float, default=30.0)
    parser.add_argument("--start", default="2024-11-01T00:00:00+00:00")
    parser.add_argument("--end", default="2024-12-31T23:59:59+00:00")
    parser.add_argument("--simulate-restart", action="store_true")
    return parser.parse_args()


class _StopFlag:
    def __init__(self) -> None:
        self.stopped = False

    def request(self, *_args: object) -> None:
        self.stopped = True

    def __call__(self) -> bool:
        return self.stopped


def _dt(raw: str) -> datetime:
    moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _load_yaml_snapshot(path: Path) -> dict:
    """Best-effort config snapshot for agent_runs/paper_trading_runs — an empty
    dict when the file is missing, never fabricated."""
    if not path.is_file():
        return {}
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def build_loop(runtime: Path, config, proposal_client, operator) -> tuple[PaperTradingLoop, SimulatedBroker]:
    halt_flag = runtime / "control" / "halt.flag"
    kill = KillSwitch(halt_flag)
    limits = load_risk_limits(REPO_ROOT / "config" / "risk_limits.yaml")
    rules, asset_classes = load_instrument_rules(REPO_ROOT / "config" / "universe.yaml")
    risk = RiskEngine(limits, rules, asset_classes, kill)
    breaker = CircuitBreaker(limits.circuit_breaker, kill)
    # Paper nu are un cost model live cu spread — folosim spread-ul de bază Kraken
    # (1x, 15bps) ca aproximare documentată (docs/risk-management.md).
    tracker = PortfolioTracker(
        config.starting_cash, config.instrument, "crypto", spread_bps=BASE_SPREAD_BPS
    )
    broker = SimulatedBroker()

    # EXECUTION_STORE_BACKEND=json|postgres (default json), mirrors MARKET_DATA_STORE_BACKEND
    # / RESEARCH_STORE_BACKEND (docs/database-cutover-playbook.md). The rollback path (json)
    # is unaffected by any of this — only the postgres branch resolves ids and constructs a
    # PostgresPortfolioStore.
    execution_backend = os.environ.get("EXECUTION_STORE_BACKEND", "json").strip().lower()
    database_url = os.environ.get("EXECUTION_DATABASE_URL")
    portfolio_id = None
    strategy_version_id = None
    risk_limits_version_id = None
    postgres_portfolio_store = None
    is_llm = not isinstance(proposal_client, BaselineProposalClient)
    if execution_backend == "postgres":
        from src.execution.postgres_store import (
            resolve_active_strategy_version_id,
            resolve_open_risk_limits_version_id,
            resolve_portfolio_id,
        )

        if not database_url:
            raise SystemExit(
                "EXECUTION_DATABASE_URL is required when EXECUTION_STORE_BACKEND=postgres"
            )
        # The runtime directory name is the seeded portfolio name (scripts/db/seed.py
        # PAPER_PORTFOLIOS: paper, paper-kraken, paper-csv, paper-faza5).
        portfolio_id = resolve_portfolio_id(database_url, runtime.name)
        strategy_id = "llm_assisted" if is_llm else "baseline_ema_cross"
        strategy_version_id = resolve_active_strategy_version_id(database_url, strategy_id)
        risk_limits_version_id = resolve_open_risk_limits_version_id(database_url)
        postgres_portfolio_store = open_portfolio_store(
            database_url=database_url,
            portfolio_id=portfolio_id,
            signal_source="llm" if is_llm else "ema_cross",
            risk_limits_version_id=risk_limits_version_id,
        )

    store = open_idempotency_store(
        backend=execution_backend,
        sqlite_path=runtime / "execution" / "idempotency.sqlite",
        database_url=database_url,
        portfolio_id=portfolio_id,
        strategy_version_id=strategy_version_id,
        risk_limits_version_id=risk_limits_version_id,
    )
    gateway = OrderGateway(store, broker)
    # AUDIT_STORE_BACKEND=files|postgres (Faza 7, docs/database-cutover-playbook.md
    # domain 5). SQLite write is unconditional either way (open_audit_log's `files`
    # branch is the plain AuditLog); postgres additionally INSERTs into audit_log.
    # Must match .env.control's AUDIT_STORE_BACKEND — both processes write the same
    # audit_log table.
    audit_backend = os.environ.get("AUDIT_STORE_BACKEND", "files").strip().lower()
    audit_database_url = os.environ.get("AUDIT_DATABASE_URL")
    audit = open_audit_log(
        runtime / "audit" / "audit.sqlite",
        backend=audit_backend,
        database_url=audit_database_url,
    )
    approval_store = None
    if audit_backend == "postgres":
        from src.audit.postgres_store import PostgresApprovalStore
        from src.db.config import require_database_url

        approval_store = PostgresApprovalStore(
            require_database_url(audit_database_url, variable="AUDIT_DATABASE_URL")
        )
    heartbeat = Heartbeat(runtime / "heartbeat" / "paper-engine.json")
    last_bar = runtime / "control" / "last_bar.json"
    recon_path = runtime / "control" / "reconciliation.json"
    local_state = runtime / "control" / "local_positions.json"
    reconciliation = Reconciliation(recon_path)
    watchdog = Watchdog(
        kill_switch=kill,
        last_bar_path=last_bar,
        reconciliation_path=recon_path,
    )
    gate = ApprovalGate(
        runtime / "control" / "approvals",
        timeout_s=config.approval_timeout_s,
        poll_interval_s=0.01,
        operator=operator,
        approval_store=approval_store,
    )
    loop = PaperTradingLoop(
        config=config,
        risk_engine=risk,
        circuit_breaker=breaker,
        kill_switch=kill,
        proposal_client=proposal_client,
        tracker=tracker,
        gateway=gateway,
        broker=broker,
        approval_gate=gate,
        audit=audit,
        heartbeat=heartbeat,
        watchdog=watchdog,
        reconciliation=reconciliation,
        last_bar_path=last_bar,
        local_state_path=local_state,
        postgres_portfolio=postgres_portfolio_store,
        strategy_version_id=strategy_version_id,
    )
    return loop, broker


def main() -> None:
    args = _parse_args()
    assert_no_kraken_trading_keys()
    config = load_paper_trading_config(args.config)
    # Construiește config-ul Nautilus (Kraken data public + sandbox exec) ca
    # verificare de wiring — bucla paper folosește SimulatedBroker, echivalentul
    # dry_run, ca ApprovalGate/audit să rămână pe calea noastră.
    node_config = build_paper_node_config(config)
    assert node_config.data_clients
    assert node_config.exec_clients

    runtime = Path(args.runtime_dir) if args.runtime_dir else REPO_ROOT / "runtime" / "paper"
    runtime.mkdir(parents=True, exist_ok=True)

    if args.skip_llm:
        client: object = BaselineProposalClient(
            fast_period=config.fast_ema_period,
            slow_period=config.slow_ema_period,
        )
    else:
        client = LLMProposalClient(base_url=args.llm_url, timeout_s=120.0)

    operator = (
        ScriptedApprovalOperator(approved=True, decided_by="paper-operator")
        if args.operator == "scripted"
        else None
    )
    loop, broker = build_loop(runtime, config, client, operator)

    # agent_runs (Faza 7): one row per engine process lifetime. Gated on BOTH
    # AUDIT_STORE_BACKEND=postgres (the writer role/table) AND
    # EXECUTION_STORE_BACKEND=postgres (loop._strategy_version_id is only ever a
    # resolved UUID on that path — agent_runs.strategy_version_id is NOT NULL, so
    # this never guesses a value when it can't be resolved).
    agent_run_store = None
    agent_run_id = None
    audit_backend = os.environ.get("AUDIT_STORE_BACKEND", "files").strip().lower()
    if (
        audit_backend == "postgres"
        and loop._postgres is not None  # noqa: SLF001
        and loop._strategy_version_id is not None  # noqa: SLF001
    ):
        import socket

        from src.audit.postgres_store import PostgresAgentRunStore, current_git_commit
        from src.db.config import require_database_url

        audit_database_url = require_database_url(
            os.environ.get("AUDIT_DATABASE_URL"), variable="AUDIT_DATABASE_URL"
        )
        agent_run_store = PostgresAgentRunStore(audit_database_url)
        agent_run_id = agent_run_store.start_run(
            portfolio_id=loop._postgres.portfolio_id,  # noqa: SLF001
            strategy_version_id=loop._strategy_version_id,  # noqa: SLF001
            trading_mode="paper",
            config_snapshot={
                "paper_trading": _load_yaml_snapshot(Path(args.config)),
                "risk_limits": _load_yaml_snapshot(REPO_ROOT / "config" / "risk_limits.yaml"),
            },
            git_commit=current_git_commit(REPO_ROOT),
            host=socket.gethostname(),
            pid=os.getpid(),
        )

    started = time.perf_counter()
    n_bars = 0
    data_source = "kraken_public_ohlc"
    stop_reason = "completed"

    try:
        if args.mode == "stream":
            if args.csv:
                raise SystemExit("stream mode does not accept --csv; use batch for replay")
            source = KrakenPublicOHLCSource()
            data_source = "kraken_public_ohlc_stream"

            def poll(_after: datetime | None) -> list:
                now = datetime.now(timezone.utc)
                delta = timeframe_delta(config.timeframe)
                start = now - delta * (config.lookback_bars + 2)
                return source.closed_bars(
                    config.instrument, start, config.timeframe, now=now
                )

            flag = _StopFlag()
            signal.signal(signal.SIGTERM, flag.request)
            signal.signal(signal.SIGINT, flag.request)
            try:
                result = loop.run_stream(
                    poll,
                    poll_interval_s=args.poll_interval_s,
                    should_stop=flag,
                )
            finally:
                source.close()
            n_bars = len(loop._history)  # noqa: SLF001 — summary only
            restart_ok = None
            stop_reason = "signal_stopped" if flag.stopped else "stream_ended"
        else:
            if args.csv:
                bars = CsvBarDataSource(Path(args.csv)).fetch_bars(
                    config.instrument, _dt(args.start), _dt(args.end), config.timeframe
                )
                data_source = f"csv:{args.csv}"
            else:
                bars = KrakenPublicOHLCSource().fetch_bars(
                    config.instrument, _dt(args.start), _dt(args.end), config.timeframe
                )
                data_source = "kraken_public_ohlc"
            n_bars = len(bars)
            max_sessions = args.max_sessions or config.session_count_target
            result = loop.run_bars(bars, max_sessions=max_sessions)
            restart_ok = None
            if args.simulate_restart:
                snapshot = broker.snapshot()
                restored = SimulatedBroker()
                restored.restore(snapshot)
                report = loop._reconciliation.reconcile(  # noqa: SLF001 — restart check in CLI
                    loop._local_snapshot(),  # noqa: SLF001
                    restored.snapshot(),
                )
                restart_ok = report.matched
                result.restart_reconciled = restart_ok
    except BaseException as exc:
        stop_reason = f"error:{type(exc).__name__}"
        raise
    finally:
        if agent_run_store is not None and agent_run_id is not None:
            agent_run_store.finish_run(agent_run_id, stop_reason=stop_reason)

    elapsed_s = time.perf_counter() - started

    sessions_payload = [
        {
            "session_index": s.session_index,
            "correlation_id": str(s.correlation_id),
            "bar_timestamp": s.bar_timestamp.isoformat(),
            "instrument": s.instrument,
            "proposal_direction": s.proposal_direction,
            "rejected_reason": s.rejected_reason,
            "risk_approved": s.risk_approved,
            "human_approved": s.human_approved,
            "order_status": s.order_status,
            "halted": s.halted,
            "notes": s.notes,
        }
        for s in result.sessions
    ]
    summary = {
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "path": config.path,
        "dry_run": config.dry_run,
        "venue": config.venue,
        "instrument": config.instrument,
        "data_source": data_source,
        "mode": args.mode,
        "n_bars": n_bars,
        "n_sessions": len(result.sessions),
        "elapsed_s": round(elapsed_s, 4),
        "latency_per_session_s": round(elapsed_s / max(len(result.sessions), 1), 4),
        "halted": any(s.halted for s in result.sessions),
        "restart_reconciled": restart_ok,
        "node_data_clients": list(node_config.data_clients),
        "node_exec_clients": list(node_config.exec_clients),
        "sessions": sessions_payload,
    }
    out = runtime / "paper_run_summary.json"
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "sessions"}, indent=2))
    print(f"Wrote {out} ({len(result.sessions)} sessions)")

    # Faza 6: paper_trading_runs upsert, piggy-backing on EXECUTION_STORE_BACKEND
    # (no separate flag — docs/database-design.md §8.6). loop._postgres is the same
    # PostgresPortfolioStore constructed in build_loop() when EXECUTION_STORE_BACKEND=
    # postgres; None on the json (rollback) path, so this is skipped entirely then.
    if loop._postgres is not None and loop._strategy_version_id is not None:  # noqa: SLF001
        from src.execution.postgres_store import PostgresPaperRunStore

        database_url = os.environ["EXECUTION_DATABASE_URL"]
        risk_limits_raw = _load_yaml_snapshot(REPO_ROOT / "config" / "risk_limits.yaml")
        paper_config_raw = _load_yaml_snapshot(Path(args.config))
        paper_run_store = PostgresPaperRunStore(database_url)
        try:
            paper_run_store.upsert_run(
                portfolio_id=loop._postgres.portfolio_id,  # noqa: SLF001
                strategy_version_id=loop._strategy_version_id,  # noqa: SLF001
                instrument=config.instrument,
                config_snapshot={
                    "paper_trading": paper_config_raw,
                    "risk_limits": risk_limits_raw,
                },
                status="halted" if summary["halted"] else "running",
                halt_reason=(
                    next((s.notes for s in result.sessions if s.halted), None)
                    if summary["halted"]
                    else None
                ),
                summary=summary,
            )
        finally:
            paper_run_store.close()


if __name__ == "__main__":
    main()
