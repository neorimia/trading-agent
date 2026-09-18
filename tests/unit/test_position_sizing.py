"""size_position e o funcție pură: fără I/O, fără input din LLM."""

from __future__ import annotations

from decimal import Decimal

from src.risk.portfolio_state import InstrumentRules
from src.risk.position_sizing import size_position

LOT1 = InstrumentRules(
    min_notional=Decimal("1"),
    lot_size=Decimal("1"),
    tick_size=Decimal("0.01"),
)
CRYPTO = InstrumentRules(
    min_notional=Decimal("10"),
    lot_size=Decimal("0.0001"),
    tick_size=Decimal("0.01"),
)


def test_notional_cap_binds() -> None:
    qty = size_position(
        cap_notional=Decimal("1000"),
        price=Decimal("100"),
        risk_budget=Decimal("10000"),
        stop_distance=Decimal("1"),
        cost_estimate=Decimal("0"),
        slippage_buffer=Decimal("0"),
        instrument_rules=LOT1,
    )
    assert qty == Decimal("10")


def test_risk_budget_binds() -> None:
    qty = size_position(
        cap_notional=Decimal("10000"),
        price=Decimal("100"),
        risk_budget=Decimal("50"),
        stop_distance=Decimal("2"),
        cost_estimate=Decimal("0"),
        slippage_buffer=Decimal("0"),
        instrument_rules=LOT1,
    )
    assert qty == Decimal("25")


def test_cost_and_slippage_widen_stop_and_reduce_qty() -> None:
    qty = size_position(
        cap_notional=Decimal("10000"),
        price=Decimal("100"),
        risk_budget=Decimal("50"),
        stop_distance=Decimal("2"),
        cost_estimate=Decimal("1"),
        slippage_buffer=Decimal("1"),
        instrument_rules=LOT1,
    )
    assert qty == Decimal("12")


def test_rounds_down_to_lot_size() -> None:
    qty = size_position(
        cap_notional=Decimal("1000"),
        price=Decimal("100"),
        risk_budget=Decimal("10000"),
        stop_distance=Decimal("1"),
        cost_estimate=Decimal("0"),
        slippage_buffer=Decimal("0"),
        instrument_rules=InstrumentRules(
            min_notional=Decimal("1"),
            lot_size=Decimal("3"),
            tick_size=Decimal("0.01"),
        ),
    )
    # raw 10, floor to lots of 3 → 9
    assert qty == Decimal("9")


def test_below_min_notional_returns_zero() -> None:
    qty = size_position(
        cap_notional=Decimal("5"),
        price=Decimal("100"),
        risk_budget=Decimal("10000"),
        stop_distance=Decimal("1"),
        cost_estimate=Decimal("0"),
        slippage_buffer=Decimal("0"),
        instrument_rules=InstrumentRules(
            min_notional=Decimal("50"),
            lot_size=Decimal("1"),
            tick_size=Decimal("0.01"),
        ),
    )
    assert qty == Decimal("0")


def test_exact_min_notional_is_accepted() -> None:
    qty = size_position(
        cap_notional=Decimal("100"),
        price=Decimal("100"),
        risk_budget=Decimal("10000"),
        stop_distance=Decimal("1"),
        cost_estimate=Decimal("0"),
        slippage_buffer=Decimal("0"),
        instrument_rules=InstrumentRules(
            min_notional=Decimal("100"),
            lot_size=Decimal("1"),
            tick_size=Decimal("0.01"),
        ),
    )
    assert qty == Decimal("1")


def test_crypto_lot_fraction() -> None:
    qty = size_position(
        cap_notional=Decimal("1000"),
        price=Decimal("2000"),
        risk_budget=Decimal("10000"),
        stop_distance=Decimal("1"),
        cost_estimate=Decimal("0"),
        slippage_buffer=Decimal("0"),
        instrument_rules=CRYPTO,
    )
    assert qty == Decimal("0.5")


def test_zero_price_returns_zero() -> None:
    qty = size_position(
        cap_notional=Decimal("1000"),
        price=Decimal("0"),
        risk_budget=Decimal("100"),
        stop_distance=Decimal("1"),
        cost_estimate=Decimal("0"),
        slippage_buffer=Decimal("0"),
        instrument_rules=LOT1,
    )
    assert qty == Decimal("0")


def test_zero_per_unit_risk_returns_zero() -> None:
    qty = size_position(
        cap_notional=Decimal("1000"),
        price=Decimal("100"),
        risk_budget=Decimal("100"),
        stop_distance=Decimal("0"),
        cost_estimate=Decimal("0"),
        slippage_buffer=Decimal("0"),
        instrument_rules=LOT1,
    )
    assert qty == Decimal("0")
