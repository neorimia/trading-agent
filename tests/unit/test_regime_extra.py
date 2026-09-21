"""Direcție, volatilitate, volum, șocuri și tagging per-bară — pure, fără look-ahead."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.data.sources import Bar
from src.engine.regime import (
    classify_direction,
    classify_volatility,
    classify_volume,
    detect_shock,
    tag_regimes,
)

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _bar(index: int, close: Decimal, *, high=None, low=None, volume=Decimal("100")) -> Bar:
    return Bar(
        instrument="ETHUSD",
        timestamp=START + timedelta(hours=index),
        open=close,
        high=high if high is not None else close + Decimal("0.5"),
        low=low if low is not None else close - Decimal("0.5"),
        close=close,
        volume=volume,
    )


def _rising_bars(n: int, step: Decimal = Decimal("1")) -> list[Bar]:
    price = Decimal("100")
    bars = []
    for i in range(n):
        bars.append(_bar(i, price))
        price += step
    return bars


def _falling_bars(n: int, step: Decimal = Decimal("1")) -> list[Bar]:
    price = Decimal("100")
    bars = []
    for i in range(n):
        bars.append(_bar(i, price))
        price -= step
    return bars


def _flat_bars(n: int) -> list[Bar]:
    bars = []
    for i in range(n):
        wobble = Decimal("0.05") if i % 2 == 0 else Decimal("-0.05")
        bars.append(_bar(i, Decimal("100") + wobble))
    return bars


def test_classify_direction_bull_bear_sideways_and_unknown() -> None:
    assert classify_direction(_rising_bars(25, step=Decimal("1"))) == "bull"
    assert classify_direction(_falling_bars(25, step=Decimal("1"))) == "bear"
    assert classify_direction(_flat_bars(25)) == "sideways"
    assert classify_direction(_rising_bars(5)) == "unknown"


def test_classify_volatility_high_low_and_unknown() -> None:
    # mișcare mare relativ la preț -> high; bare flat -> low; prea puține bare -> unknown
    volatile = []
    price = Decimal("100")
    for i in range(20):
        price += Decimal("5") if i % 2 == 0 else Decimal("-5")
        volatile.append(_bar(i, price, high=price + Decimal("3"), low=price - Decimal("3")))
    assert classify_volatility(volatile) == "high"
    quiet = []
    price = Decimal("100")
    for i in range(20):
        wobble = Decimal("0.05") if i % 2 == 0 else Decimal("-0.05")
        p = price + wobble
        quiet.append(_bar(i, p, high=p + Decimal("0.05"), low=p - Decimal("0.05")))
    assert classify_volatility(quiet) == "low"
    assert classify_volatility(_rising_bars(5)) == "unknown"


def test_classify_volume_high_low_and_unknown() -> None:
    bars = []
    for i in range(25):
        vol = Decimal("1000") if i == 24 else Decimal("100")
        bars.append(_bar(i, Decimal("100"), volume=vol))
    assert classify_volume(bars) == "high"

    low_bars = []
    for i in range(25):
        vol = Decimal("1") if i == 24 else Decimal("100")
        low_bars.append(_bar(i, Decimal("100"), volume=vol))
    assert classify_volume(low_bars) == "low"

    assert classify_volume(_rising_bars(5)) == "unknown"


def test_detect_shock_true_on_large_jump_false_otherwise() -> None:
    calm = _flat_bars(20)
    assert detect_shock(calm) is False
    shocked = _flat_bars(20) + [_bar(20, Decimal("150"))]
    assert detect_shock(shocked) is True


def test_tag_regimes_returns_one_tag_per_bar_with_timestamps_aligned() -> None:
    bars = _rising_bars(30)
    tags = tag_regimes(bars)
    assert len(tags) == len(bars)
    assert all(tag.timestamp == bar.timestamp for tag, bar in zip(tags, bars))
    # bara 0 nu are destul istoric pentru niciun clasificator
    assert tags[0].direction == "unknown"
    assert tags[0].trend == "unknown"


def test_tag_regimes_does_not_leak_future_bars() -> None:
    bars = _rising_bars(40)
    poisoned = list(bars)
    cutoff = 20
    for i in range(cutoff + 1, len(bars)):
        poisoned[i] = _bar(i, Decimal("999999"))
    clean_tags = tag_regimes(bars[: cutoff + 1])
    dirty_tags = tag_regimes(poisoned[: cutoff + 1])
    assert clean_tags == dirty_tags
