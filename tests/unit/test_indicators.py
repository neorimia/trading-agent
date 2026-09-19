"""Indicatori deterministi: fără look-ahead, fără LLM."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.data.sources import Bar
from src.engine.indicators import (
    aggregate_weekly,
    atr,
    bars_upto,
    indicator_snapshot,
    rsi,
    technical_facts_bundle,
    volume_zscore,
)


def _bars(n: int, *, start: datetime | None = None) -> list[Bar]:
    origin = start or datetime(2026, 8, 1, tzinfo=timezone.utc)
    out: list[Bar] = []
    price = Decimal("2400")
    for index in range(n):
        stamp = origin + timedelta(days=index)
        price += Decimal("1")
        out.append(
            Bar(
                instrument="ETHUSD",
                timestamp=stamp,
                open=price,
                high=price + Decimal("10"),
                low=price - Decimal("10"),
                close=price,
                volume=Decimal("100") + Decimal(index),
            )
        )
    return out


def test_rsi_atr_ready_after_enough_bars() -> None:
    bars = _bars(30)
    closes = [bar.close for bar in bars]
    assert rsi(closes) is not None
    assert atr(bars) is not None
    assert volume_zscore([bar.volume for bar in bars]) is not None


def test_indicators_do_not_use_future_bars() -> None:
    bars = _bars(30)
    as_of = bars[20].timestamp
    sliced = bars_upto(bars, as_of)
    assert sliced[-1].timestamp == as_of
    assert all(bar.timestamp <= as_of for bar in sliced)
    snap = indicator_snapshot(sliced, timeframe="1d")
    assert snap["close"] == format(bars[20].close, "f")
    assert snap["close"] != format(bars[-1].close, "f")


def test_weekly_aggregation_uses_last_close_time() -> None:
    bars = _bars(14)
    weekly = aggregate_weekly(bars)
    assert len(weekly) >= 2
    assert weekly[0].timestamp <= weekly[-1].timestamp


def test_facts_bundle_marks_missing_derivatives_unknown() -> None:
    bars = _bars(25)
    bundle = technical_facts_bundle(
        {"1d": bars},
        instrument="ETHUSD",
        as_of=bars[-1].timestamp,
    )
    assert bundle["funding"] == "unknown"
    assert bundle["open_interest"] == "unknown"
    assert "1w" in bundle["indicators"]
    assert bundle["indicators"]["1d"]["instrument"] == "ETHUSD"
