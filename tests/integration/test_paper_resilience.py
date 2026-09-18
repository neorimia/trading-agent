"""Cazuri explicite Faza 5: reconnect, stale, reject/partial, timeout, duplicate."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from src.execution.broker import SimulatedBroker
from src.execution.idempotency_store import IdempotencyStore
from src.execution.order_gateway import OrderGateway
from src.execution.reconciliation import LocalPortfolioSnapshot, Reconciliation
from src.execution.types import OrderRequest
from src.monitor.watchdog import Watchdog
from src.risk.kill_switch import KillSwitch
from tests.integration.test_paper_trading_flow import _bars, build_loop


def test_reconnect_after_restart_reconciles(tmp_path: Path) -> None:
    loop, _audit, broker, halt = build_loop(tmp_path)
    result = loop.run_bars(_bars(), max_sessions=1)
    assert result.sessions[0].order_status == "filled"
    qty = broker.snapshot().positions["ETHUSD"]
    restored = SimulatedBroker()
    restored.restore(broker.snapshot())
    recon = Reconciliation(tmp_path / "recon.json")
    report = recon.reconcile(
        LocalPortfolioSnapshot(positions={"ETHUSD": qty}),
        restored.snapshot(),
    )
    assert report.matched is True
    assert halt.is_active() is False

    mismatched = recon.reconcile(
        LocalPortfolioSnapshot(positions={"ETHUSD": qty + Decimal("1")}),
        restored.snapshot(),
    )
    assert mismatched.matched is False


def test_stale_data_trips_watchdog(tmp_path: Path) -> None:
    halt = KillSwitch(tmp_path / "halt.flag")
    last_bar = tmp_path / "last_bar.json"
    last_bar.write_text(
        '{"timestamp": "2020-01-01T00:00:00+00:00"}',
        encoding="utf-8",
    )
    watchdog = Watchdog(
        kill_switch=halt,
        last_bar_path=last_bar,
        reconciliation_path=tmp_path / "recon.json",
    )
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    assert watchdog.check_stale_data(60, now=now) is True
    watchdog.set_halt("stale_data")
    assert halt.is_active() is True


def test_rejected_and_partial_fills(tmp_path: Path) -> None:
    reject_id = uuid4()
    partial_id = uuid4()
    broker = SimulatedBroker()
    broker.set_last_price("ETHUSD", Decimal("2500"))
    broker.set_outcome(str(reject_id), "rejected")
    broker.set_outcome(str(partial_id), "partially_filled")
    gateway = OrderGateway(IdempotencyStore(tmp_path / "idemp.sqlite"), broker)

    rejected = gateway.submit(
        OrderRequest(
            client_order_id=reject_id,
            instrument="ETHUSD",
            side="buy",
            quantity=Decimal("0.5"),
            order_type="market",
        )
    )
    partial = gateway.submit(
        OrderRequest(
            client_order_id=partial_id,
            instrument="ETHUSD",
            side="buy",
            quantity=Decimal("0.5"),
            order_type="market",
        )
    )
    assert rejected.status == "rejected"
    assert partial.status == "partially_filled"
    assert partial.filled_quantity == Decimal("0.2")
    assert broker.snapshot().positions["ETHUSD"] == Decimal("0.2")


def test_post_submit_timeout_halts(tmp_path: Path) -> None:
    broker = SimulatedBroker(default_outcome="timeout")
    loop, audit, _broker, halt = build_loop(tmp_path, broker=broker)
    result = loop.run_bars(_bars(), max_sessions=1)
    assert result.sessions[0].order_status == "timeout"
    assert result.sessions[0].halted is True
    assert halt.is_active() is True
    types = [event.event_type for event in audit.list_events()]
    assert "halt" in types
    assert "order_submitted" in types


def test_duplicate_client_order_id_does_not_resubmit(tmp_path: Path) -> None:
    broker = SimulatedBroker()
    broker.set_last_price("ETHUSD", Decimal("2500"))
    gateway = OrderGateway(IdempotencyStore(tmp_path / "idemp.sqlite"), broker)
    order = OrderRequest(
        client_order_id=uuid4(),
        instrument="ETHUSD",
        side="buy",
        quantity=Decimal("0.25"),
        order_type="market",
    )
    first = gateway.submit(order)
    second = gateway.submit(order)
    assert first.status == "filled"
    assert second == first
    assert broker.snapshot().positions["ETHUSD"] == Decimal("0.25")
