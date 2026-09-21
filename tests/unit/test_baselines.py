"""Baseline-uri: buy&hold, cash, equal-weight, random control — cifre cunoscute + seed fix."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.data.sources import Bar
from src.engine.baselines import (
    buy_and_hold_equity_curve,
    buy_and_hold_return_pct,
    cash_return_pct,
    equal_weight_return_pct,
    random_control_return_pct,
)

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _bars(closes: list[str]) -> list[Bar]:
    return [
        Bar(
            instrument="ETHUSD",
            timestamp=START + timedelta(days=i),
            open=Decimal(c),
            high=Decimal(c),
            low=Decimal(c),
            close=Decimal(c),
            volume=Decimal("100"),
        )
        for i, c in enumerate(closes)
    ]


def test_buy_and_hold_return_pct_exact() -> None:
    bars = _bars(["100", "105", "110"])
    result = buy_and_hold_return_pct(bars)
    assert result == Decimal("10")


def test_buy_and_hold_returns_none_for_short_or_zero_series() -> None:
    assert buy_and_hold_return_pct([]) is None
    assert buy_and_hold_return_pct(_bars(["100"])) is None


def test_buy_and_hold_equity_curve_scales_starting_cash() -> None:
    bars = _bars(["100", "200"])
    curve = buy_and_hold_equity_curve(bars, Decimal("1000"))
    assert curve[0][1] == Decimal("1000")
    assert curve[1][1] == Decimal("2000")


def test_cash_return_is_always_zero() -> None:
    assert cash_return_pct() == Decimal("0")


def test_equal_weight_return_is_mean_of_inputs() -> None:
    result = equal_weight_return_pct({"ETHUSD": Decimal("10"), "BTCUSD": Decimal("-2")})
    assert result == Decimal("4")


def test_equal_weight_return_none_when_empty() -> None:
    assert equal_weight_return_pct({}) is None


def test_random_control_is_reproducible_with_fixed_seed() -> None:
    bars = _bars([str(100 + i) for i in range(50)])
    first = random_control_return_pct(bars, trade_rate=0.3, seed=42)
    second = random_control_return_pct(bars, trade_rate=0.3, seed=42)
    assert first == second


def test_random_control_differs_with_different_seed() -> None:
    bars = _bars([str(100 + (i % 5) - 2) for i in range(50)])
    first = random_control_return_pct(bars, trade_rate=0.3, seed=42)
    second = random_control_return_pct(bars, trade_rate=0.3, seed=7)
    assert first != second


def test_random_control_none_for_zero_trade_rate_or_short_series() -> None:
    bars = _bars(["100", "101"])
    assert random_control_return_pct(bars, trade_rate=0.0) is None
    assert random_control_return_pct([], trade_rate=0.5) is None
