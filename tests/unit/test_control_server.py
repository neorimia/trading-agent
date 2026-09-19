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
from src.control.server import ControlContext, create_app, validate_bind_host
from src.control.settings import load_control_settings
from src.data.sources import Bar
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


def test_auth_token_required_when_configured(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, environ={"CONTROL_OPERATOR_TOKEN": "local-token"})
    with _client(ctx) as client:
        denied = client.get("/v1/health")
        ok = client.get("/v1/health", headers={"Authorization": "Bearer local-token"})
    assert denied.status_code == 401
    assert ok.status_code == 200
