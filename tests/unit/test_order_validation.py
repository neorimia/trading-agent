"""Validare lot / notional înainte de submit live."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from src.data.venue_registry import constraints_for
from src.execution.order_validation import validate_order_constraints
from src.execution.types import OrderRequest


def _order(quantity: Decimal) -> OrderRequest:
    return OrderRequest(
        client_order_id=uuid4(),
        instrument="ETHUSD",
        side="buy",
        quantity=quantity,
        order_type="market",
    )


def test_aligned_quantity_passes() -> None:
    constraints = constraints_for("ETHUSD")
    assert (
        validate_order_constraints(
            _order(Decimal("0.01")),
            constraints,
            last_price=Decimal("2500"),
        )
        is None
    )


def test_unaligned_lot_rejected() -> None:
    constraints = constraints_for("ETHUSD")
    reason = validate_order_constraints(
        _order(Decimal("0.00015")),
        constraints,
        last_price=Decimal("2500"),
    )
    assert reason == "quantity_not_aligned_to_lot_size"


def test_notional_too_small() -> None:
    constraints = constraints_for("ETHUSD")
    reason = validate_order_constraints(
        _order(Decimal("0.0001")),
        constraints,
        last_price=Decimal("1"),
    )
    assert reason == "notional_below_minimum"
