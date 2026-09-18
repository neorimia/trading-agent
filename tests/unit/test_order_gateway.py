"""OrderGateway — idempotent pe client_order_id, cancel_all."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from src.execution.broker import SimulatedBroker
from src.execution.idempotency_store import IdempotencyStore
from src.execution.order_gateway import OrderGateway
from src.execution.types import OrderRequest


def _gateway(tmp_path: Path, broker: SimulatedBroker | None = None) -> tuple[OrderGateway, SimulatedBroker]:
    sim = broker if broker is not None else SimulatedBroker()
    sim.set_last_price("ETHUSD", Decimal("2500"))
    store = IdempotencyStore(tmp_path / "idemp.sqlite")
    return OrderGateway(store, sim), sim


def _order(order_id=None) -> OrderRequest:
    return OrderRequest(
        client_order_id=order_id or uuid4(),
        instrument="ETHUSD",
        side="buy",
        quantity=Decimal("0.1"),
        order_type="market",
    )


def test_submit_fills_and_is_idempotent(tmp_path: Path) -> None:
    gateway, _broker = _gateway(tmp_path)
    order = _order()
    first = gateway.submit(order)
    second = gateway.submit(order)
    assert first.status == "filled"
    assert first.filled_quantity == Decimal("0.1")
    assert second == first


def test_duplicate_does_not_double_fill(tmp_path: Path) -> None:
    gateway, broker = _gateway(tmp_path)
    order = _order()
    gateway.submit(order)
    gateway.submit(order)
    assert broker.snapshot().positions["ETHUSD"] == Decimal("0.1")


def test_cancel_all_clears_open_orders(tmp_path: Path) -> None:
    broker = SimulatedBroker()
    broker.set_last_price("ETHUSD", Decimal("2500"))
    order = _order()
    broker.set_outcome(str(order.client_order_id), "timeout")
    gateway, _ = _gateway(tmp_path, broker)
    result = gateway.submit(order)
    assert result.status == "timeout"
    assert broker.snapshot().open_client_order_ids
    gateway.cancel_all("test")
    assert broker.snapshot().open_client_order_ids == []
