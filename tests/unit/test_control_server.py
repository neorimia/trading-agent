"""Control plane: loopback API, fără secrete, fără /propose."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.audit.audit_log import AuditLog
from src.audit.events import AuditEvent
from src.control.agent_process import NullAgentProcess
from src.control.runtime_state import halt_if_heartbeat_stale
from src.control.server import ControlContext, create_app, validate_bind_host
from src.control.settings import load_control_settings
from src.data.market_data_registry import MarketDataAdapterRegistry
from src.data.sources import Bar
from src.discovery.models import AssetCandidate, CandidateFactors, DiscoveryRun, SourceRef
from src.discovery.store import append_run as append_discovery_run
from src.engine.analysis_types import ParsedAnalysis, RejectedAnalysis
from src.monitor.heartbeat import Heartbeat
from src.research.models import ResearchDocument
from src.research.store import MetadataStore
from src.risk.kill_switch import KillSwitch

REPO_ROOT = Path(__file__).resolve().parents[2]


def _bars(symbol: str = "ETHUSD") -> list[Bar]:
    stamps = [
        datetime(2026, 9, 1, tzinfo=timezone.utc),
        datetime(2026, 9, 2, tzinfo=timezone.utc),
        datetime(2026, 9, 3, tzinfo=timezone.utc),
    ]
    closes = [Decimal("2400"), Decimal("2420"), Decimal("2410")]
    out = []
    for stamp, close in zip(stamps, closes, strict=True):
        out.append(
            Bar(
                instrument=symbol,
                timestamp=stamp,
                open=close,
                high=close + Decimal("10"),
                low=close - Decimal("10"),
                close=close,
                volume=Decimal("100"),
            )
        )
    return out


def _ctx(tmp_path: Path, **overrides: object) -> ControlContext:
    runtime = tmp_path / "runtime"
    shutil.copy(REPO_ROOT / "config" / "risk_limits.yaml", tmp_path / "risk_limits.yaml")
    shutil.copy(REPO_ROOT / "config" / "universe.yaml", tmp_path / "universe.yaml")
    shutil.copy(REPO_ROOT / "config" / "paper_trading.yaml", tmp_path / "paper_trading.yaml")
    shutil.copy(REPO_ROOT / "config" / "strategies.yaml", tmp_path / "strategies.yaml")
    environ = {
        "CONTROL_SERVER_HOST": "127.0.0.1",
        "RUNTIME_DIR": str(runtime),
        "HALT_FLAG_PATH": str(runtime / "control" / "halt.flag"),
        "RISK_LIMITS_PATH": str(tmp_path / "risk_limits.yaml"),
        "UNIVERSE_PATH": str(tmp_path / "universe.yaml"),
        "PAPER_CONFIG_PATH": str(tmp_path / "paper_trading.yaml"),
        "STRATEGIES_PATH": str(tmp_path / "strategies.yaml"),
        "RESEARCH_METADATA_DB_PATH": str(tmp_path / "research.db"),
        "BROKER_PAPER_MODE": "true",
        "LIVE_TRADING_ENABLED": "false",
        "ENVIRONMENT": "test",
        "CONTROL_OPERATOR_ROLE": "operator",
    }
    extra_env = overrides.pop("environ", {})
    assert isinstance(extra_env, dict)
    environ.update(extra_env)
    settings = load_control_settings(root=tmp_path, environ=environ)
    ctx = ControlContext(
        settings=settings,
        environ=environ,
        fetch_bars=lambda instrument, start, end, timeframe: _bars(instrument),
        ping=lambda url: "8765" in url,
        alive=lambda pid: settings.paths.agent_pid.is_file(),
        process=NullAgentProcess(),
        now=lambda: datetime(2026, 9, 18, 12, tzinfo=timezone.utc),
    )
    for key, value in overrides.items():
        setattr(ctx, key, value)
    return ctx


def _client(ctx: ControlContext) -> TestClient:
    return TestClient(create_app(ctx))


def test_validate_bind_host_accepts_loopback() -> None:
    assert validate_bind_host("127.0.0.1") == "127.0.0.1"


def test_validate_bind_host_rejects_wildcard() -> None:
    with pytest.raises(ValueError, match="loopback"):
        validate_bind_host("0.0.0.0")


def test_health_stopped_paper(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        response = client.get("/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["agent"] == "stopped"
    assert body["trading_mode"] == "paper"
    assert body["llm"] == "up"
    assert body["research"] == "down"
    assert body["live_actions_blocked"] is True
    assert body["broker_monitor"]["status"] == "not_configured"
    assert body["broker_monitor"]["mode"] == "monitor"


def test_broker_monitor_endpoint_not_configured(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        response = client.get("/v1/broker/monitor")
    assert response.status_code == 200
    assert response.json()["status"] == "not_configured"


def test_emergency_halt_writes_flag(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        response = client.post(
            "/v1/risk/halt",
            json={"reason": "operator_stop"},
            headers={"Idempotency-Key": "halt-1"},
        )
        health = client.get("/v1/health")
    assert response.status_code == 200
    assert KillSwitch(ctx.settings.paths.halt_flag).is_active()
    assert health.json()["agent"] == "halted"
    assert health.json()["halt_reason"] == "operator_stop"


def test_halt_if_heartbeat_stale_triggers_halt_for_running_agent(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    ctx.settings.paths.agent_pid.parent.mkdir(parents=True, exist_ok=True)
    ctx.settings.paths.agent_pid.write_text("4242", encoding="utf-8")
    stale_moment = datetime(2026, 9, 18, 11, 0, tzinfo=timezone.utc)  # 1h before ctx.now()
    Heartbeat(ctx.settings.paths.heartbeat).write("paper-engine", stale_moment)

    triggered = halt_if_heartbeat_stale(ctx.settings, now=ctx.now(), ping=ctx.ping, alive=ctx.alive)

    assert triggered is True
    assert KillSwitch(ctx.settings.paths.halt_flag).is_active()


def test_halt_if_heartbeat_stale_leaves_fresh_heartbeat_alone(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    ctx.settings.paths.agent_pid.parent.mkdir(parents=True, exist_ok=True)
    ctx.settings.paths.agent_pid.write_text("4242", encoding="utf-8")
    Heartbeat(ctx.settings.paths.heartbeat).write("paper-engine", ctx.now())

    triggered = halt_if_heartbeat_stale(ctx.settings, now=ctx.now(), ping=ctx.ping, alive=ctx.alive)

    assert triggered is False
    assert KillSwitch(ctx.settings.paths.halt_flag).is_active() is False


def test_halt_if_heartbeat_stale_ignores_stopped_agent(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    stale_moment = datetime(2026, 9, 18, 11, 0, tzinfo=timezone.utc)
    Heartbeat(ctx.settings.paths.heartbeat).write("paper-engine", stale_moment)

    triggered = halt_if_heartbeat_stale(ctx.settings, now=ctx.now(), ping=ctx.ping, alive=ctx.alive)

    assert triggered is False
    assert KillSwitch(ctx.settings.paths.halt_flag).is_active() is False


def test_halt_is_idempotent(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        first = client.post(
            "/v1/risk/halt",
            json={"reason": "operator_stop"},
            headers={"Idempotency-Key": "same"},
        )
        second = client.post(
            "/v1/risk/halt",
            json={"reason": "other"},
            headers={"Idempotency-Key": "same"},
        )
    assert first.json() == second.json()


def test_approval_writes_same_decision_file_as_cli(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    cid = uuid4()
    directory = ctx.settings.paths.approvals_dir
    directory.mkdir(parents=True)
    last_bar = {
        "instrument": "ETHUSD",
        "bar_timestamp": "2026-09-18T12:00:00+00:00",
        "timestamp": "2026-09-18T12:00:00+00:00",
        "close": "2410",
    }
    ctx.settings.paths.last_bar.parent.mkdir(parents=True, exist_ok=True)
    ctx.settings.paths.last_bar.write_text(json.dumps(last_bar), encoding="utf-8")
    (directory / f"{cid}.request.json").write_text(
        json.dumps(
            {
                "correlation_id": str(cid),
                "requested_at": "2026-09-18T11:30:00+00:00",
                "risk_decision": {
                    "approved": True,
                    "instrument": "ETHUSD",
                    "side": "buy",
                    "quantity": "0.1",
                    "reject_reason": None,
                    "requires_human_approval": True,
                },
            }
        ),
        encoding="utf-8",
    )
    ctx.settings.paths.agent_pid.parent.mkdir(parents=True, exist_ok=True)
    ctx.settings.paths.agent_pid.write_text("4242", encoding="utf-8")
    with _client(ctx) as client:
        pending = client.get("/v1/approvals/pending")
        decide = client.post(
            f"/v1/approvals/{cid}",
            json={"approved": True, "reason": "manual", "decided_by": "human"},
            headers={"Idempotency-Key": "appr-1"},
        )
    assert pending.status_code == 200
    assert pending.json()[0]["instrument"] == "ETHUSD"
    assert decide.status_code == 200
    decision = json.loads((directory / f"{cid}.decision.json").read_text(encoding="utf-8"))
    assert decision["approved"] is True
    assert decision["decided_by"] == "human"
    assert decision["reason"] == "manual"


def test_approve_blocked_when_halted(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    cid = uuid4()
    directory = ctx.settings.paths.approvals_dir
    directory.mkdir(parents=True)
    (directory / f"{cid}.request.json").write_text(
        json.dumps(
            {
                "correlation_id": str(cid),
                "requested_at": "2026-09-18T11:00:00+00:00",
                "risk_decision": {
                    "approved": True,
                    "instrument": "ETHUSD",
                    "side": "buy",
                    "quantity": "0.1",
                    "reject_reason": None,
                    "requires_human_approval": True,
                },
            }
        ),
        encoding="utf-8",
    )
    KillSwitch(ctx.settings.paths.halt_flag).trigger("test")
    with _client(ctx) as client:
        response = client.post(
            f"/v1/approvals/{cid}",
            json={"approved": True, "reason": "manual", "decided_by": "human"},
            headers={"Idempotency-Key": "appr-halt"},
        )
    assert response.status_code == 409


def test_settings_never_leaks_secrets(tmp_path: Path) -> None:
    secret = "super-secret-kraken-key"
    ctx = _ctx(
        tmp_path,
        environ={
            "KRAKEN_SPOT_API_KEY": secret,
            "KRAKEN_SPOT_API_SECRET": "super-secret-kraken-secret",
        },
    )
    with _client(ctx) as client:
        response = client.get("/v1/settings/security")
    assert response.status_code == 200
    text = response.text
    assert secret not in text
    assert "super-secret-kraken-secret" not in text
    assert response.json()["kraken_spot_key_present"] is True


def test_mutation_requires_idempotency_key(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        response = client.post("/v1/risk/halt", json={"reason": "x"})
    assert response.status_code == 400


def test_observer_cannot_halt(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, environ={"CONTROL_OPERATOR_ROLE": "observer"})
    with _client(ctx) as client:
        response = client.post(
            "/v1/risk/halt",
            json={"reason": "x"},
            headers={"Idempotency-Key": "obs"},
        )
    assert response.status_code == 403


def test_live_start_blocked(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, environ={"LIVE_TRADING_ENABLED": "true"})
    with _client(ctx) as client:
        response = client.post("/v1/agent/start", headers={"Idempotency-Key": "live"})
        health = client.get("/v1/health")
    assert response.status_code == 403
    assert health.json()["trading_mode"] == "live"


def test_agent_start_stop_pid_file(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        start = client.post("/v1/agent/start", headers={"Idempotency-Key": "start"})
        health = client.get("/v1/health")
        stop = client.post("/v1/agent/stop", headers={"Idempotency-Key": "stop"})
    assert start.status_code == 200
    assert health.json()["agent"] == "running"
    assert stop.status_code == 200
    assert not ctx.settings.paths.agent_pid.is_file()


def test_risk_put_requires_confirmation_token(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    body = {
        "max_notional_per_order": "1000",
        "max_exposure_per_instrument": "2000",
        "max_exposure_per_asset_class": "5000",
        "max_daily_loss": "150",
        "max_drawdown": "500",
        "max_orders_per_day": 10,
        "circuit_breaker": {
            "max_consecutive_errors": 3,
            "max_consecutive_losses": 3,
            "halt_on_unknown_order_result": True,
        },
        "confirmation_token": "WRONG",
    }
    with _client(ctx) as client:
        denied = client.put(
            "/v1/risk/limits", json=body, headers={"Idempotency-Key": "risk-bad"}
        )
        body["confirmation_token"] = "MAX_DAILY_LOSS"
        ok = client.put(
            "/v1/risk/limits", json=body, headers={"Idempotency-Key": "risk-ok"}
        )
        view = client.get("/v1/risk/limits")
    assert denied.status_code == 422
    assert ok.status_code == 200
    assert ok.json()["restart_required"] is True
    assert view.json()["max_daily_loss"] == "150"


def test_market_and_signal_from_injected_bars(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        market = client.get("/v1/market")
        bars = client.get("/v1/market/ETHUSD/bars?timeframe=1d")
        signal = client.get("/v1/signals?symbol=ETHUSD")
    assert market.status_code == 200
    eth = next(item for item in market.json() if item["symbol"] == "ETHUSD")
    assert eth["price"] == "2410"
    assert bars.json()["bars"][-1]["close"] == "2410"
    assert "ema_fast" in bars.json()["bars"][-1]
    assert signal.json()["is_proposal"] is True


class _CryptoOnlySource:
    def fetch_bars(self, instrument: str, start: datetime, end: datetime, timeframe: str) -> list[Bar]:
        return _bars(instrument)


def test_market_surfaces_typed_status_for_research_only_symbol(tmp_path: Path) -> None:
    """Regresie root cause: un simbol fără venue de execuție (AAPL) nu dispare silențios."""
    registry = MarketDataAdapterRegistry(adapters={"KRAKEN": _CryptoOnlySource})
    ctx = _ctx(tmp_path, fetch_bars=registry.fetch_bars)
    _write_last_bar(ctx)
    with _client(ctx) as client:
        market = client.get("/v1/market")
    assert market.status_code == 200
    rows = {item["symbol"]: item for item in market.json()}
    assert rows["AAPL"]["status"] == "research_only"
    assert rows["AAPL"]["stale"] is True
    assert rows["AAPL"]["price"] is None
    assert rows["ETHUSD"]["status"] == "ok"
    assert rows["ETHUSD"]["stale"] is False


def test_portfolio_and_orders_from_audit(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    log = AuditLog(ctx.settings.paths.audit_db)
    cid = uuid4()
    log.record(
        AuditEvent.now(
            correlation_id=cid,
            event_type="order_submitted",
            payload={
                "client_order_id": str(cid),
                "instrument": "ETHUSD",
                "side": "buy",
                "quantity": "0.2",
                "status": "filled",
                "fill_price": "2400",
                "filled_quantity": "0.2",
            },
        )
    )
    log.record(
        AuditEvent.now(
            correlation_id=cid,
            event_type="fill",
            payload={
                "instrument": "ETHUSD",
                "side": "buy",
                "filled_quantity": "0.2",
                "fill_price": "2400",
                "status": "filled",
            },
        )
    )
    ctx.settings.paths.local_positions.parent.mkdir(parents=True, exist_ok=True)
    ctx.settings.paths.local_positions.write_text(
        json.dumps({"positions": {"ETHUSD": "0.2"}, "pending_client_order_ids": []}),
        encoding="utf-8",
    )
    ctx.settings.paths.last_bar.parent.mkdir(parents=True, exist_ok=True)
    ctx.settings.paths.last_bar.write_text(
        json.dumps(
            {
                "instrument": "ETHUSD",
                "bar_timestamp": "2026-09-18T12:00:00+00:00",
                "timestamp": "2026-09-18T12:00:00+00:00",
                "close": "2410",
            }
        ),
        encoding="utf-8",
    )
    with _client(ctx) as client:
        portfolio = client.get("/v1/portfolio")
        orders = client.get("/v1/orders")
        events = client.get("/v1/agent/events")
        positions = client.get("/v1/positions")
    assert portfolio.status_code == 200
    assert Decimal(portfolio.json()["cash"]) < Decimal("10000")
    assert orders.json()
    assert events.json()["events"]
    assert positions.json()[0]["instrument"] == "ETHUSD"


def test_research_documents_include_contradictions(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    store = MetadataStore(ctx.settings.paths.research_db)
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    first = ResearchDocument(
        doc_id="doc-1",
        url="https://example.com/a",
        title="Rates steady",
        source_id="fred",
        author=None,
        published_at=now,
        fetched_at=now,
        event_date=None,
        assets_mentioned=["ETHUSD"],
        category="macro_indicator",
        extracted_text="Held rates.",
        summary="held",
        sentiment_score=0.1,
        impact_magnitude="low",
        impact_direction="neutral",
        confidence_score=0.7,
        last_verified_at=now,
        content_hash="h1",
    )
    second = ResearchDocument(
        doc_id="doc-2",
        url="https://example.com/b",
        title="Rates cut",
        source_id="reuters_rss",
        author=None,
        published_at=now,
        fetched_at=now,
        event_date=None,
        assets_mentioned=["ETHUSD"],
        category="news",
        extracted_text="Cut rates.",
        summary="cut",
        sentiment_score=-0.2,
        impact_magnitude="high",
        impact_direction="bullish",
        confidence_score=0.4,
        last_verified_at=now,
        content_hash="h2",
    )
    store.upsert(first)
    store.upsert(second)
    store._conn.execute(
        "INSERT INTO document_relations (doc_id, related_doc_id, relation_type) VALUES (?,?,?)",
        ("doc-1", "doc-2", "contradicts"),
    )
    store._conn.commit()
    store.close()
    with _client(ctx) as client:
        response = client.get("/v1/research/documents?instrument=ETHUSD")
    assert response.status_code == 200
    docs = response.json()
    assert any(doc["contradicts"] for doc in docs)


def test_strategy_toggle_requires_token(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        listed = client.get("/v1/strategies")
        denied = client.post(
            "/v1/strategies/llm_assisted",
            json={"enabled": True, "confirmation_token": "nope"},
            headers={"Idempotency-Key": "st-bad"},
        )
        ok = client.post(
            "/v1/strategies/llm_assisted",
            json={"enabled": True, "confirmation_token": "ENABLE_STRATEGY"},
            headers={"Idempotency-Key": "st-ok"},
        )
    assert listed.json()[0]["id"] == "baseline_ema_cross"
    assert denied.status_code == 422
    assert ok.json()["restart_required"] is True


def test_strategy_list_includes_version_status_and_hypothesis(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        response = client.get("/v1/strategies")
    rows = response.json()
    baseline = next(row for row in rows if row["id"] == "baseline_ema_cross")
    assert baseline["status"] == "experimental"
    assert baseline["version"] == 1
    assert baseline["hypothesis"]
    assert "ETHUSD" in baseline["supported_assets"]


def test_strategy_backtest_start_requires_token(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        denied = client.post(
            "/v1/strategies/baseline_ema_cross/backtests",
            json={
                "universe_symbol": "ETHUSD",
                "timeframe": "1d",
                "start": "2024-11-01T00:00:00Z",
                "end": "2024-12-16T00:00:00Z",
                "cost_multiplier": 1,
                "confirmation_token": "nope",
            },
            headers={"Idempotency-Key": "bt-bad"},
        )
    assert denied.status_code == 422


def test_strategy_backtest_start_unknown_strategy_returns_404(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        response = client.post(
            "/v1/strategies/does-not-exist/backtests",
            json={
                "universe_symbol": "ETHUSD",
                "timeframe": "1d",
                "start": "2024-11-01T00:00:00Z",
                "end": "2024-12-16T00:00:00Z",
                "cost_multiplier": 1,
                "confirmation_token": "RUN_BACKTEST",
            },
            headers={"Idempotency-Key": "bt-404"},
        )
    assert response.status_code == 404


def test_strategy_backtest_start_rejects_llm_kind(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        response = client.post(
            "/v1/strategies/llm_assisted/backtests",
            json={
                "universe_symbol": "ETHUSD",
                "timeframe": "1d",
                "start": "2024-11-01T00:00:00Z",
                "end": "2024-12-16T00:00:00Z",
                "cost_multiplier": 1,
                "confirmation_token": "RUN_BACKTEST",
            },
            headers={"Idempotency-Key": "bt-llm"},
        )
    assert response.status_code == 422
    assert "cannot run via the async backtest job" in response.json()["detail"]


def test_strategy_backtest_full_lifecycle_queued_then_visible_in_list_and_status(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        started = client.post(
            "/v1/strategies/baseline_ema_cross/backtests",
            json={
                "universe_symbol": "ETHUSD",
                "timeframe": "1d",
                "start": "2024-11-01T00:00:00Z",
                "end": "2024-12-16T00:00:00Z",
                "cost_multiplier": 1,
                "confirmation_token": "RUN_BACKTEST",
            },
            headers={"Idempotency-Key": "bt-run-1"},
        )
        assert started.status_code == 200
        run_id = started.json()["run_id"]
        assert started.json()["status"] == "queued"

        # worker-ul e async; procesăm sincron ca să nu depindem de timing în test.
        ctx.backtest_jobs().process_one(timeout_s=5)

        status = client.get(f"/v1/strategies/baseline_ema_cross/backtests/{run_id}")
        assert status.status_code == 200
        record = status.json()
        assert record["status"] == "done"
        assert record["metrics"]["comparable"]["n_bars"] == 3

        listing = client.get("/v1/strategies/baseline_ema_cross/backtests")
        assert listing.status_code == 200
        assert any(row["run_id"] == run_id for row in listing.json())

        missing = client.get(f"/v1/strategies/baseline_ema_cross/backtests/{run_id}-nope")
        assert missing.status_code == 404


def test_strategy_backtest_status_mismatched_strategy_returns_404(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        started = client.post(
            "/v1/strategies/baseline_ema_cross/backtests",
            json={
                "universe_symbol": "ETHUSD",
                "timeframe": "1d",
                "start": "2024-11-01T00:00:00Z",
                "end": "2024-12-16T00:00:00Z",
                "cost_multiplier": 1,
                "confirmation_token": "RUN_BACKTEST",
            },
            headers={"Idempotency-Key": "bt-run-2"},
        )
        run_id = started.json()["run_id"]
        wrong_strategy = client.get(f"/v1/strategies/donchian_breakout/backtests/{run_id}")
    assert wrong_strategy.status_code == 404


def test_strategy_version_write_requires_token(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        denied = client.post(
            "/v1/strategies/baseline_ema_cross/versions",
            json={
                "params": {"fast_ema_period": 8, "slow_ema_period": 21},
                "change_note": "tighten fast EMA",
                "confirmation_token": "nope",
            },
            headers={"Idempotency-Key": "ver-bad"},
        )
    assert denied.status_code == 422


def test_strategy_version_write_rejects_invalid_params(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        response = client.post(
            "/v1/strategies/baseline_ema_cross/versions",
            json={
                "params": {"fast_ema_period": -1, "slow_ema_period": 20},
                "change_note": "bad params",
                "confirmation_token": "EDIT_STRATEGY",
            },
            headers={"Idempotency-Key": "ver-invalid"},
        )
    assert response.status_code == 422


def test_strategy_version_write_creates_new_version_and_is_listed(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        first = client.post(
            "/v1/strategies/baseline_ema_cross/versions",
            json={
                "params": {"fast_ema_period": 9, "slow_ema_period": 20},
                "change_note": "initial snapshot in this fresh env",
                "confirmation_token": "EDIT_STRATEGY",
            },
            headers={"Idempotency-Key": "ver-ok-1"},
        )
        assert first.status_code == 200
        assert first.json()["restart_required"] is True

        second = client.post(
            "/v1/strategies/baseline_ema_cross/versions",
            json={
                "params": {"fast_ema_period": 8, "slow_ema_period": 21},
                "change_note": "tighten fast EMA",
                "confirmation_token": "EDIT_STRATEGY",
            },
            headers={"Idempotency-Key": "ver-ok-2"},
        )
        assert second.status_code == 200

        versions = client.get("/v1/strategies/baseline_ema_cross/versions")
        assert versions.status_code == 200
        rows = versions.json()
        assert [row["version"] for row in rows] == [1, 2]
        assert rows[-1]["params"]["fast_ema_period"] == 8
        assert rows[-1]["change_note"] == "tighten fast EMA"

        listed = client.get("/v1/strategies")
        row = next(item for item in listed.json() if item["id"] == "baseline_ema_cross")
        assert row["version"] == 2
        assert row["params"]["fast_ema_period"] == "8"


def test_strategy_version_write_can_mark_status_without_changing_params(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        write = client.post(
            "/v1/strategies/baseline_ema_cross/versions",
            json={
                "params": {"fast_ema_period": 10, "slow_ema_period": 20},
                "status": "paper_candidate",
                "change_note": "promoted after OOS review",
                "confirmation_token": "EDIT_STRATEGY",
            },
            headers={"Idempotency-Key": "ver-status"},
        )
        assert write.status_code == 200

        listed = client.get("/v1/strategies")
        row = next(item for item in listed.json() if item["id"] == "baseline_ema_cross")
        assert row["status"] == "paper_candidate"
        assert row["version"] == 1


def test_strategy_version_write_unknown_strategy_returns_404(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        response = client.post(
            "/v1/strategies/does-not-exist/versions",
            json={
                "params": {},
                "change_note": "x",
                "confirmation_token": "EDIT_STRATEGY",
            },
            headers={"Idempotency-Key": "ver-404"},
        )
    assert response.status_code == 404


def test_strategy_clone_requires_token(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        response = client.post(
            "/v1/strategies/donchian_breakout/clone",
            json={"new_id": "donchian_breakout_copy", "confirmation_token": "nope"},
            headers={"Idempotency-Key": "clone-bad"},
        )
    assert response.status_code == 422


def test_strategy_clone_creates_disabled_experimental_copy(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        cloned = client.post(
            "/v1/strategies/donchian_breakout/clone",
            json={"new_id": "donchian_breakout_copy", "confirmation_token": "CLONE_STRATEGY"},
            headers={"Idempotency-Key": "clone-ok"},
        )
        assert cloned.status_code == 200

        listed = client.get("/v1/strategies")
        row = next(item for item in listed.json() if item["id"] == "donchian_breakout_copy")
        assert row["enabled"] is False
        assert row["status"] == "experimental"
        assert row["version"] == 1

        versions = client.get("/v1/strategies/donchian_breakout_copy/versions")
        assert len(versions.json()) == 1


def test_strategy_clone_duplicate_id_rejected(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        response = client.post(
            "/v1/strategies/donchian_breakout/clone",
            json={"new_id": "baseline_ema_cross", "confirmation_token": "CLONE_STRATEGY"},
            headers={"Idempotency-Key": "clone-dup"},
        )
    assert response.status_code == 422


def test_strategy_clone_unknown_source_returns_404(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        response = client.post(
            "/v1/strategies/does-not-exist/clone",
            json={"new_id": "whatever", "confirmation_token": "CLONE_STRATEGY"},
            headers={"Idempotency-Key": "clone-404"},
        )
    assert response.status_code == 404


def test_websocket_emits_health_channel(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        with client.websocket_connect("/v1/ws/events") as ws:
            message = ws.receive_json()
    assert message["channel"] == "health"
    assert message["payload"]["trading_mode"] == "paper"


def test_websocket_rejects_missing_token_after_accept(tmp_path: Path) -> None:
    from starlette.websockets import WebSocketDisconnect

    ctx = _ctx(tmp_path, environ={"CONTROL_OPERATOR_TOKEN": "local-token"})
    with _client(ctx) as client:
        with client.websocket_connect("/v1/ws/events") as ws:
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
    assert exc.value.code == 1008


def test_websocket_rejects_cross_origin(tmp_path: Path) -> None:
    from starlette.websockets import WebSocketDisconnect

    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        with client.websocket_connect(
            "/v1/ws/events", headers={"origin": "http://evil.example"}
        ) as ws:
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
    assert exc.value.code == 1008


def test_websocket_allows_configured_origin(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        with client.websocket_connect(
            "/v1/ws/events", headers={"origin": ctx.settings.cors_origins[0]}
        ) as ws:
            message = ws.receive_json()
    assert message["channel"] == "health"


def test_auth_token_required_when_configured(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, environ={"CONTROL_OPERATOR_TOKEN": "local-token"})
    with _client(ctx) as client:
        denied = client.get("/v1/health")
        ok = client.get("/v1/health", headers={"Authorization": "Bearer local-token"})
    assert denied.status_code == 401
    assert ok.status_code == 200


def _parsed_analysis() -> ParsedAnalysis:
    return ParsedAnalysis.model_validate(
        {
            "asset": "ETHUSD",
            "timestamp": "2026-09-18T12:00:00+00:00",
            "timeframe": "1d",
            "analysis_type": "technical",
            "factual_summary": "EMA fast above slow.",
            "data_sources": [{"url": "kraken:ohlc"}],
            "bullish_case": "hold",
            "bearish_case": "break",
            "neutral_case": "range",
            "key_assumptions": ["spot"],
            "catalysts": ["unknown"],
            "risks": ["liquidity"],
            "invalidation_conditions": ["close below slow"],
            "confidence_score": 0.4,
            "data_quality_score": 0.6,
            "uncertainty": "no funding",
            "recommended_action": "hold",
            "action_type": "research_only",
            "position_size_suggestion": None,
            "required_human_approval": True,
            "expiry_time": "2026-09-19T12:00:00+00:00",
            "audit_metadata": {
                "model_name": "qwen3:8b",
                "prompt_hash": "aa",
                "facts_bundle_hash": "bb",
                "temperature": 0.0,
                "schema_version": "analysis.v1",
            },
        }
    )


def test_indicators_endpoint_is_not_an_order(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        response = client.get("/v1/market/ETHUSD/indicators", params={"timeframe": "1d"})
    assert response.status_code == 200
    body = response.json()
    assert body["is_order"] is False
    assert body["snapshot"]["instrument"] == "ETHUSD"
    assert body["snapshot"]["funding"] == "unknown"


def test_stress_endpoint_is_deterministic(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        response = client.get("/v1/portfolio/stress")
    assert response.status_code == 200
    body = response.json()
    assert body["is_order"] is False
    assert body["options_available"] is False
    assert body["hedge_universe"] == "spot_only_kraken"
    assert {item["name"] for item in body["scenarios"]} >= {
        "crypto_spot_down_10",
        "crypto_bear_20",
    }


def test_daily_plan_does_not_invent_calendar_events(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        response = client.get("/v1/research/daily-plan", params={"instrument": "ETHUSD"})
    assert response.status_code == 200
    body = response.json()
    assert body["is_order"] is False
    calendar = next(item for item in body["checklist"] if item["item"] == "economic / protocol calendar")
    assert calendar["value"] == ["none listed"]


def test_operator_analyze_is_research_only(tmp_path: Path) -> None:
    captured: list[object] = []

    def _analyze(context):
        captured.append(context.analysis_type)
        return _parsed_analysis()

    ctx = _ctx(tmp_path, request_analysis=_analyze)
    with _client(ctx) as client:
        response = client.post(
            "/v1/research/analyze",
            json={"instrument": "ETHUSD", "analysis_type": "technical", "timeframe": "1d"},
            headers={"Idempotency-Key": "analyze-1"},
        )
        listed = client.get("/v1/research/analyses", params={"instrument": "ETHUSD"})
    assert response.status_code == 200
    body = response.json()
    assert body["is_order"] is False
    assert body["analysis"]["position_size_suggestion"] is None
    assert body["analysis"]["required_human_approval"] is True
    assert captured == ["technical"]
    assert listed.json()[0]["is_order"] is False


def test_analyze_rejects_non_level1_type(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, request_analysis=lambda context: _parsed_analysis())
    with _client(ctx) as client:
        response = client.post(
            "/v1/research/analyze",
            json={"instrument": "ETHUSD", "analysis_type": "stress", "timeframe": "1d"},
            headers={"Idempotency-Key": "analyze-stress"},
        )
    assert response.status_code == 422


def test_observer_cannot_run_analysis(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, environ={"CONTROL_OPERATOR_ROLE": "observer"})
    with _client(ctx) as client:
        response = client.post(
            "/v1/research/analyze",
            json={"instrument": "ETHUSD", "analysis_type": "technical", "timeframe": "1d"},
            headers={"Idempotency-Key": "analyze-obs"},
        )
    assert response.status_code == 403


def _discovery_factors(**overrides: object) -> CandidateFactors:
    defaults = dict(
        notional_volume_24h_usd="1000000",
        spread_bps=5.0,
        liquidity_score=0.8,
        spread_score=0.9,
        volatility=0.02,
        data_quality_score=1.0,
        operational_risk_score=0.1,
        correlation_btc=0.5,
        correlation_eth=0.4,
        min_order_notional_usd="10",
        listing_age_days=400,
        exchange_status="online",
    )
    defaults.update(overrides)
    return CandidateFactors.model_validate(defaults)


def _seed_discovery_candidate(ctx: ControlContext, **overrides: object) -> AssetCandidate:
    now = ctx.now()
    defaults = dict(
        asset="XXBTZUSD",
        asset_class="crypto",
        exchange="KRAKEN",
        timestamp=now,
        research_horizon="swing (days-weeks)",
        candidate_status="research",
        opportunity_score=0.7,
        risk_score=0.2,
        confidence_score=0.8,
        data_quality_score=1.0,
        factors=_discovery_factors(),
        sources=[SourceRef(source_id="kraken_public_api", url="https://api.kraken.com/0/public", fetched_at=now)],
        expires_at=now,
    )
    defaults.update(overrides)
    candidate = AssetCandidate.model_validate(defaults)
    append_discovery_run(
        DiscoveryRun(run_at=now, exchange=candidate.exchange, candidates=[candidate], rejected=[]),
        ctx.settings.paths.discovery_store,
    )
    return candidate


def _discovery_analysis(**overrides: object) -> ParsedAnalysis:
    defaults = dict(
        asset="XXBTZUSD",
        timestamp="2026-09-18T12:00:00+00:00",
        timeframe="swing (days-weeks)",
        analysis_type="discovery",
        factual_summary="Liquidity and spread pass the eligibility filters.",
        data_sources=[],
        bullish_case="Liquidity score is above the peer median.",
        bearish_case="Volatility is elevated versus the reference window.",
        neutral_case="Correlation with BTC limits diversification benefit.",
        key_assumptions=["Kraken spot only"],
        catalysts=["unknown"],
        risks=["operational risk score above median"],
        invalidation_conditions=["exchange status leaves online"],
        confidence_score=0.4,
        data_quality_score=0.8,
        uncertainty="News sentiment and catalyst score are not yet computed.",
        recommended_action="research_more",
        action_type="research_only",
        position_size_suggestion=None,
        required_human_approval=True,
        expiry_time="2026-09-19T12:00:00+00:00",
        audit_metadata={
            "model_name": "qwen3:8b",
            "prompt_hash": "aa",
            "facts_bundle_hash": "bb",
            "temperature": 0.0,
            "schema_version": "analysis.v1",
        },
    )
    defaults.update(overrides)
    return ParsedAnalysis.model_validate(defaults)


def test_discovery_candidates_empty_store(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        response = client.get("/v1/discovery/candidates")
    assert response.status_code == 200
    assert response.json() == []


def test_discovery_candidates_lists_seeded_candidate(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    _seed_discovery_candidate(ctx)
    with _client(ctx) as client:
        response = client.get("/v1/discovery/candidates")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == "KRAKEN:XXBTZUSD"
    assert "composite_rank" in body[0]


def test_discovery_candidate_detail_returns_candidate(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    _seed_discovery_candidate(ctx)
    with _client(ctx) as client:
        response = client.get("/v1/discovery/candidates/XXBTZUSD")
    assert response.status_code == 200
    body = response.json()
    assert body["asset"] == "XXBTZUSD"
    assert "composite_rank" in body


def test_discovery_candidate_detail_missing_is_404(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        response = client.get("/v1/discovery/candidates/UNKNOWN")
    assert response.status_code == 404


def test_discovery_summarize_missing_candidate_is_404(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, request_discovery_summary=lambda context: _discovery_analysis())
    with _client(ctx) as client:
        response = client.post(
            "/v1/discovery/candidates/UNKNOWN/summarize",
            headers={"Idempotency-Key": "disc-missing"},
        )
    assert response.status_code == 404


def test_discovery_summarize_accepts_clean_narrative(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, request_discovery_summary=lambda context: _discovery_analysis())
    _seed_discovery_candidate(ctx)
    with _client(ctx) as client:
        response = client.post(
            "/v1/discovery/candidates/XXBTZUSD/summarize",
            headers={"Idempotency-Key": "disc-1"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["bullish_case"] == ["Liquidity score is above the peer median."]
    assert body["missing_data"] == []
    assert body["sources"][-1]["source_id"] == "llm_discovery_summary"
    assert "composite_rank" in body


def test_discovery_summarize_rejects_forbidden_phrase(tmp_path: Path) -> None:
    ctx = _ctx(
        tmp_path,
        request_discovery_summary=lambda context: _discovery_analysis(
            bullish_case="This will definitely go up."
        ),
    )
    _seed_discovery_candidate(ctx)
    with _client(ctx) as client:
        response = client.post(
            "/v1/discovery/candidates/XXBTZUSD/summarize",
            headers={"Idempotency-Key": "disc-forbidden"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["bullish_case"] == []
    assert "llm_summary_rejected:forbidden_phrase" in body["missing_data"]


def test_discovery_summarize_surfaces_llm_rejection(tmp_path: Path) -> None:
    ctx = _ctx(
        tmp_path,
        request_discovery_summary=lambda context: RejectedAnalysis(reason="timeout", raw_output=""),
    )
    _seed_discovery_candidate(ctx)
    with _client(ctx) as client:
        response = client.post(
            "/v1/discovery/candidates/XXBTZUSD/summarize",
            headers={"Idempotency-Key": "disc-rejected"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["bullish_case"] == []
    assert "llm_summary_rejected:timeout" in body["missing_data"]


def test_discovery_summarize_requires_operator(tmp_path: Path) -> None:
    ctx = _ctx(
        tmp_path,
        environ={"CONTROL_OPERATOR_ROLE": "observer"},
        request_discovery_summary=lambda context: _discovery_analysis(),
    )
    _seed_discovery_candidate(ctx)
    with _client(ctx) as client:
        response = client.post(
            "/v1/discovery/candidates/XXBTZUSD/summarize",
            headers={"Idempotency-Key": "disc-obs"},
        )
    assert response.status_code == 403


def _write_last_bar(ctx: ControlContext, instrument: str = "ETHUSD", close: str = "2410") -> None:
    ctx.settings.paths.last_bar.parent.mkdir(parents=True, exist_ok=True)
    ctx.settings.paths.last_bar.write_text(
        json.dumps(
            {
                "instrument": instrument,
                "bar_timestamp": "2026-09-18T12:00:00+00:00",
                "timestamp": "2026-09-18T12:00:00+00:00",
                "close": close,
            }
        ),
        encoding="utf-8",
    )


def _write_pid(ctx: ControlContext) -> None:
    ctx.settings.paths.agent_pid.parent.mkdir(parents=True, exist_ok=True)
    ctx.settings.paths.agent_pid.write_text("4242", encoding="utf-8")


def test_health_venue_stale_when_running_without_bar(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    _write_pid(ctx)
    with _client(ctx) as client:
        body = client.get("/v1/health").json()
    assert body["agent"] == "running"
    assert body["venue"] == "stale"


def test_health_venue_down_when_stopped_without_bar(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    with _client(ctx) as client:
        body = client.get("/v1/health").json()
    assert body["agent"] == "stopped"
    assert body["venue"] == "down"


def test_health_survives_truncated_last_bar(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    _write_pid(ctx)
    ctx.settings.paths.last_bar.parent.mkdir(parents=True, exist_ok=True)
    ctx.settings.paths.last_bar.write_text("{", encoding="utf-8")
    with _client(ctx) as client:
        response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json()["venue"] == "stale"


def test_portfolio_does_not_mark_other_instruments_at_last_bar(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    ctx.settings.paths.local_positions.parent.mkdir(parents=True, exist_ok=True)
    ctx.settings.paths.local_positions.write_text(
        json.dumps(
            {"positions": {"ETHUSD": "0.2", "BTCUSD": "0.1"}, "pending_client_order_ids": []}
        ),
        encoding="utf-8",
    )
    _write_last_bar(ctx)
    with _client(ctx) as client:
        body = client.get("/v1/portfolio").json()
    assert Decimal(body["exposure_per_instrument"]["ETHUSD"]) == Decimal("482.0")
    assert Decimal(body["exposure_per_instrument"]["BTCUSD"]) == Decimal("0")
    assert body["incomplete"] is True


def test_orders_include_reject_reason_without_reason_key(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    log = AuditLog(ctx.settings.paths.audit_db)
    cid = uuid4()
    log.record(
        AuditEvent.now(
            correlation_id=cid,
            event_type="risk_decision",
            payload={
                "approved": False,
                "instrument": "ETHUSD",
                "side": "buy",
                "quantity": "0",
                "reject_reason": "max_drawdown",
                "requires_human_approval": False,
            },
        )
    )
    with _client(ctx) as client:
        response = client.get("/v1/orders")
    assert response.status_code == 200
    assert response.json()[0]["reason"] == "max_drawdown"
    assert response.json()[0]["status"] == "rejected"


def test_approve_expired_is_conflict(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    cid = uuid4()
    directory = ctx.settings.paths.approvals_dir
    directory.mkdir(parents=True)
    _write_last_bar(ctx)
    _write_pid(ctx)
    (directory / f"{cid}.request.json").write_text(
        json.dumps(
            {
                "correlation_id": str(cid),
                "requested_at": "2026-09-18T10:00:00+00:00",
                "risk_decision": {
                    "approved": True,
                    "instrument": "ETHUSD",
                    "side": "buy",
                    "quantity": "0.1",
                    "reject_reason": None,
                    "requires_human_approval": True,
                },
            }
        ),
        encoding="utf-8",
    )
    with _client(ctx) as client:
        response = client.post(
            f"/v1/approvals/{cid}",
            json={"approved": True, "reason": "late", "decided_by": "human"},
            headers={"Idempotency-Key": "appr-expired"},
        )
    assert response.status_code == 409
    assert response.json()["detail"] == "approval_timeout"
    assert not (directory / f"{cid}.decision.json").is_file()


def test_reject_after_expiry_is_recorded(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    cid = uuid4()
    directory = ctx.settings.paths.approvals_dir
    directory.mkdir(parents=True)
    (directory / f"{cid}.request.json").write_text(
        json.dumps(
            {
                "correlation_id": str(cid),
                "requested_at": "2026-09-18T10:00:00+00:00",
                "risk_decision": {
                    "approved": True,
                    "instrument": "ETHUSD",
                    "side": "buy",
                    "quantity": "0.1",
                    "reject_reason": None,
                    "requires_human_approval": True,
                },
            }
        ),
        encoding="utf-8",
    )
    with _client(ctx) as client:
        response = client.post(
            f"/v1/approvals/{cid}",
            json={"approved": False, "reason": "too_late", "decided_by": "human"},
            headers={"Idempotency-Key": "appr-reject-expired"},
        )
    assert response.status_code == 200
    decision = json.loads((directory / f"{cid}.decision.json").read_text(encoding="utf-8"))
    assert decision["approved"] is False


def test_concurrent_write_approval_one_wins(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from src.control.runtime_state import write_approval

    ctx = _ctx(tmp_path)
    cid = uuid4()
    directory = ctx.settings.paths.approvals_dir
    directory.mkdir(parents=True)
    (directory / f"{cid}.request.json").write_text(
        json.dumps(
            {
                "correlation_id": str(cid),
                "requested_at": "2026-09-18T11:30:00+00:00",
                "risk_decision": {
                    "approved": True,
                    "instrument": "ETHUSD",
                    "side": "buy",
                    "quantity": "0.1",
                    "reject_reason": None,
                    "requires_human_approval": True,
                },
            }
        ),
        encoding="utf-8",
    )
    errors: list[BaseException] = []

    def _write(reason: str) -> None:
        try:
            write_approval(
                ctx.settings,
                cid,
                approved=False,
                reason=reason,
                decided_by="human",
                now=ctx.now(),
            )
        except FileExistsError as exc:
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(_write, "a")
        two = pool.submit(_write, "b")
        one.result()
        two.result()
    assert len(errors) == 1
    assert (directory / f"{cid}.decision.json").is_file()


def test_portfolio_survives_invalid_paper_config(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    ctx.settings.paths.paper_config.write_text("not: valid-paper-config\n", encoding="utf-8")
    with _client(ctx) as client:
        response = client.get("/v1/portfolio")
        positions = client.get("/v1/positions")
    assert response.status_code == 200
    assert response.json()["incomplete"] is True
    assert positions.status_code == 200


def test_websocket_survives_snapshot_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.control import server as control_server

    ctx = _ctx(tmp_path)
    calls = {"n": 0}
    real = control_server._ws_snapshot

    def flaky(snapshot_ctx, sent_at):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("torn json")
        return real(snapshot_ctx, sent_at)

    async def _no_sleep(*_args, **_kwargs):  # noqa: ANN002, ANN003
        return None

    monkeypatch.setattr(control_server, "_ws_snapshot", flaky)
    monkeypatch.setattr(control_server.asyncio, "sleep", _no_sleep)
    with _client(ctx) as client:
        with client.websocket_connect("/v1/ws/events") as ws:
            message = ws.receive_json()
    assert message["channel"] == "health"
    assert calls["n"] >= 2
