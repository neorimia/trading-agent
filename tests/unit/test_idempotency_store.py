"""IdempotencyStore.reserve — scris înainte de submit, duplicate respinse."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from src.execution.idempotency_store import DuplicateClientOrderId, IdempotencyStore
from src.execution.types import OrderResult


def test_reserve_inserts_and_duplicate_raises(tmp_path: Path) -> None:
    store = IdempotencyStore(tmp_path / "idemp.sqlite")
    order_id = uuid4()
    store.reserve(order_id)
    with pytest.raises(DuplicateClientOrderId) as exc:
        store.reserve(order_id)
    assert exc.value.stored is None
    assert order_id in store.reserved_ids()


def test_store_and_reload_result(tmp_path: Path) -> None:
    store = IdempotencyStore(tmp_path / "idemp.sqlite")
    order_id = uuid4()
    store.reserve(order_id)
    result = OrderResult(
        client_order_id=order_id,
        status="filled",
        broker_order_id="sim-1",
        filled_quantity=Decimal("0.1"),
        fill_price=Decimal("2500"),
    )
    store.store_result(result)
    loaded = store.get_result(order_id)
    assert loaded == result
    with pytest.raises(DuplicateClientOrderId) as exc:
        store.reserve(order_id)
    assert exc.value.stored == result
