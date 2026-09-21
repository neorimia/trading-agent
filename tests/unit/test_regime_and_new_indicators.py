"""Donchian channel, ADX și clasificarea de regim — pure, fără look-ahead."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.data.sources import Bar
from src.engine.indicators import adx, donchian_channel
from src.engine.regime import classify_regime

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _bar(index: int, high: Decimal, low: Decimal, close: Decimal, volume: Decimal = Decimal("100")) -> Bar:
    return Bar(
        instrument="ETHUSD",
        timestamp=START + timedelta(days=index),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _trending_bars(n: int) -> list[Bar]:
    bars = []
    price = Decimal("100")
    for i in range(n):
        price += Decimal("2")
        bars.append(_bar(i, price + Decimal("1"), price - Decimal("1"), price))
    return bars


def _flat_bars(n: int) -> list[Bar]:
    bars = []
    for i in range(n):
        wobble = Decimal("0.5") if i % 2 == 0 else Decimal("-0.5")
        price = Decimal("100") + wobble
        bars.append(_bar(i, price + Decimal("1"), price - Decimal("1"), price))
    return bars


def test_donchian_channel_none_when_insufficient_bars() -> None:
    assert donchian_channel(_trending_bars(5), period=20) is None


def test_donchian_channel_uses_only_last_period_bars() -> None:
    bars = _trending_bars(25)
    high, low, mid = donchian_channel(bars, period=20)
    window = bars[-20:]
    assert high == max(b.high for b in window)
    assert low == min(b.low for b in window)
    assert mid == (high + low) / Decimal(2)


def test_donchian_period_must_exceed_one() -> None:
    with pytest.raises(ValueError):
        donchian_channel(_trending_bars(5), period=1)


def test_adx_none_when_insufficient_bars() -> None:
    assert adx(_trending_bars(10), period=14) is None


def test_adx_positive_on_strong_trend() -> None:
    value = adx(_trending_bars(60), period=14)
    assert value is not None
    assert value > Decimal("20")


def test_adx_low_on_flat_market() -> None:
    value = adx(_flat_bars(60), period=14)
    assert value is not None
    assert value < Decimal("20")


def test_adx_rejects_non_positive_period() -> None:
    with pytest.raises(ValueError):
        adx(_trending_bars(60), period=0)


def test_classify_regime_trend() -> None:
    assert classify_regime(_trending_bars(60)) == "trend"


def test_classify_regime_range() -> None:
    assert classify_regime(_flat_bars(60)) == "range"


def test_classify_regime_unknown_when_insufficient_data() -> None:
    assert classify_regime(_trending_bars(5)) == "unknown"
