"""Dimensionare de poziție — funcție pură, fără I/O, fără input LLM."""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from src.risk.portfolio_state import InstrumentRules


def size_position(
    cap_notional: Decimal,
    price: Decimal,
    risk_budget: Decimal,
    stop_distance: Decimal,
    cost_estimate: Decimal,
    slippage_buffer: Decimal,
    instrument_rules: InstrumentRules,
) -> Decimal:
    """qty = min(cap_notional / price, risk_budget / (stop + cost + slippage)), rotunjit în jos.

    Returnează Decimal(0) dacă nu există capacitate sau dacă notional-ul cade sub minimul
    instrumentului — niciodată o cantitate „reparată" în sus.
    """
    if price <= 0 or cap_notional <= 0 or risk_budget <= 0:
        return Decimal("0")
    per_unit_risk = stop_distance + cost_estimate + slippage_buffer
    if per_unit_risk <= 0:
        return Decimal("0")

    qty_by_notional = cap_notional / price
    qty_by_risk = risk_budget / per_unit_risk
    raw_qty = min(qty_by_notional, qty_by_risk)
    qty = _floor_to_lot(raw_qty, instrument_rules.lot_size)
    if qty <= 0:
        return Decimal("0")
    if qty * price < instrument_rules.min_notional:
        return Decimal("0")
    return qty


def _floor_to_lot(qty: Decimal, lot_size: Decimal) -> Decimal:
    if lot_size <= 0 or qty <= 0:
        return Decimal("0")
    lots = (qty / lot_size).to_integral_value(rounding=ROUND_DOWN)
    return lots * lot_size
