"""CLI paper trading — Cale B, dry_run obligatoriu."""

from __future__ import annotations

import argparse
import json
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
from src.execution.idempotency_store import IdempotencyStore
from src.execution.order_gateway import OrderGateway
from src.execution.reconciliation import Reconciliation
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


def build_loop(runtime: Path, config, proposal_client, operator) -> tuple[PaperTradingLoop, SimulatedBroker]:
    halt_flag = runtime / "control" / "halt.flag"
    kill = KillSwitch(halt_flag)
    limits = load_risk_limits(REPO_ROOT / "config" / "risk_limits.yaml")
    rules, asset_classes = load_instrument_rules(REPO_ROOT / "config" / "universe.yaml")
    risk = RiskEngine(limits, rules, asset_classes, kill)
    breaker = CircuitBreaker(limits.circuit_breaker, kill)
    tracker = PortfolioTracker(config.starting_cash, config.instrument, "crypto")
    broker = SimulatedBroker()
    store = IdempotencyStore(runtime / "execution" / "idempotency.sqlite")
    gateway = OrderGateway(store, broker)
    audit = AuditLog(runtime / "audit" / "audit.sqlite")
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
    started = time.perf_counter()
    n_bars = 0
    data_source = "kraken_public_ohlc"

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


if __name__ == "__main__":
    main()
