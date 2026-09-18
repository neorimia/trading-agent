"""Validare deterministă a ordinului față de constraints (universe + AssetPairs)."""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN

from src.data.venue_registry import InstrumentConstraints
from src.execution.types import OrderRequest


def _quantize(value: Decimal, increment: Decimal) -> Decimal:
    if increment <= 0:
        raise ValueError("increment must be positive")
    steps = (value / increment).to_integral_value(rounding=ROUND_DOWN)
    return steps * increment


def validate_order_constraints(
    order: OrderRequest,
    constraints: InstrumentConstraints,
    *,
    last_price: Decimal | None,
) -> str | None:
    """Întoarce un motiv de reject sau None dacă ordinul e valid."""
    if order.quantity <= 0:
        return "quantity_not_positive"
    sized = _quantize(order.quantity, constraints.lot_size)
    if sized != order.quantity:
        return "quantity_not_aligned_to_lot_size"
    if order.quantity < constraints.min_quantity:
        return "quantity_below_minimum"
    if last_price is None or last_price <= 0:
        return "missing_price"
    notional = order.quantity * last_price
    if notional < constraints.min_notional:
        return "notional_below_minimum"
    return None
