"""Indicatori tehnici puri — fără LLM, fără look-ahead.

Apelantul trebuie să taie `bars` la T (close-time). Niciun bar cu timestamp > T.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from src.data.sources import Bar
from src.engine.signals import ema

FAST_EMA = 10
SLOW_EMA = 20


def _require_utc(moment: datetime, field_name: str) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return moment.astimezone(timezone.utc)


def _dec_or_none(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def rsi(closes: list[Decimal], period: int = 14) -> Decimal | None:
    if period <= 0:
        raise ValueError("rsi period must be positive")
    if len(closes) < period + 1:
        return None
    gains = Decimal("0")
    losses = Decimal("0")
    window = closes[-(period + 1) :]
    for previous, current in zip(window, window[1:]):
        delta = current - previous
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / Decimal(period)
    avg_loss = losses / Decimal(period)
    if avg_loss == 0:
        return Decimal("100")
    rs = avg_gain / avg_loss
    return Decimal("100") - (Decimal("100") / (Decimal("1") + rs))


def atr(bars: list[Bar], period: int = 14) -> Decimal | None:
    if period <= 0:
        raise ValueError("atr period must be positive")
    if len(bars) < period + 1:
        return None
    true_ranges: list[Decimal] = []
    window = bars[-(period + 1) :]
    for previous, current in zip(window, window[1:]):
        high_low = current.high - current.low
        high_close = abs(current.high - previous.close)
        low_close = abs(current.low - previous.close)
        true_ranges.append(max(high_low, high_close, low_close))
    return sum(true_ranges, Decimal("0")) / Decimal(period)


def volume_zscore(volumes: list[Decimal], lookback: int = 20) -> Decimal | None:
    if lookback <= 1 or len(volumes) < lookback:
        return None
    window = volumes[-lookback:]
    mean = sum(window, Decimal("0")) / Decimal(lookback)
    variance = sum((item - mean) ** 2 for item in window) / Decimal(lookback)
    if variance == 0:
        return Decimal("0")
    std = variance.sqrt()
    return (window[-1] - mean) / std


def swing_levels(bars: list[Bar], lookback: int = 20) -> tuple[Decimal | None, Decimal | None]:
    if not bars:
        return None, None
    window = bars[-lookback:] if lookback > 0 else bars
    return max(bar.high for bar in window), min(bar.low for bar in window)


def aggregate_weekly(bars: list[Bar]) -> list[Bar]:
    """Agregare ISO-week din bare zilnice. Timestamp-ul e close-time-ul ultimei zile din săptămână."""
    grouped: dict[tuple[int, int], list[Bar]] = {}
    for bar in bars:
        stamp = _require_utc(bar.timestamp, "timestamp")
        iso = stamp.isocalendar()
        grouped.setdefault((iso.year, iso.week), []).append(bar)
    weekly: list[Bar] = []
    for key in sorted(grouped):
        chunk = grouped[key]
        weekly.append(
            Bar(
                instrument=chunk[-1].instrument,
                timestamp=chunk[-1].timestamp,
                open=chunk[0].open,
                high=max(item.high for item in chunk),
                low=min(item.low for item in chunk),
                close=chunk[-1].close,
                volume=sum((item.volume for item in chunk), Decimal("0")),
            )
        )
    return weekly


def bars_upto(bars: list[Bar], as_of: datetime) -> list[Bar]:
    cutoff = _require_utc(as_of, "as_of")
    return [bar for bar in bars if _require_utc(bar.timestamp, "timestamp") <= cutoff]


def indicator_snapshot(bars: list[Bar], *, timeframe: str) -> dict[str, Any]:
    """Dict JSON-serializabil pentru facts_bundle. Nivelurile sunt calculate, nu ghicit."""
    if not bars:
        return {
            "timeframe": timeframe,
            "bar_count": 0,
            "close": "unknown",
            "ema_fast": "unknown",
            "ema_slow": "unknown",
            "rsi_14": "unknown",
            "atr_14": "unknown",
            "volume_z_20": "unknown",
            "swing_high": "unknown",
            "swing_low": "unknown",
            "as_of": "unknown",
        }
    closes = [bar.close for bar in bars]
    volumes = [bar.volume for bar in bars]
    last = bars[-1]
    fast = ema(closes, FAST_EMA) if len(closes) >= FAST_EMA else None
    slow = ema(closes, SLOW_EMA) if len(closes) >= SLOW_EMA else None
    swing_high, swing_low = swing_levels(bars)
    return {
        "timeframe": timeframe,
        "bar_count": len(bars),
        "instrument": last.instrument,
        "as_of": last.timestamp.isoformat(),
        "open": format(last.open, "f"),
        "high": format(last.high, "f"),
        "low": format(last.low, "f"),
        "close": format(last.close, "f"),
        "volume": format(last.volume, "f"),
        "ema_fast": _dec_or_none(fast) or "unknown",
        "ema_slow": _dec_or_none(slow) or "unknown",
        "rsi_14": _dec_or_none(rsi(closes)) or "unknown",
        "atr_14": _dec_or_none(atr(bars)) or "unknown",
        "volume_z_20": _dec_or_none(volume_zscore(volumes)) or "unknown",
        "swing_high": _dec_or_none(swing_high) or "unknown",
        "swing_low": _dec_or_none(swing_low) or "unknown",
        "funding": "unknown",
        "open_interest": "unknown",
    }


def technical_facts_bundle(
    bars_by_timeframe: dict[str, list[Bar]],
    *,
    instrument: str,
    as_of: datetime,
) -> dict[str, Any]:
    """Pachet factual P2. Timeframe-urile absente rămân unknown — nu se inventează."""
    cutoff = _require_utc(as_of, "as_of")
    indicators: dict[str, Any] = {}
    for timeframe, bars in bars_by_timeframe.items():
        sliced = bars_upto(bars, cutoff)
        indicators[timeframe] = indicator_snapshot(sliced, timeframe=timeframe)
    if "1d" in bars_by_timeframe and "1w" not in indicators:
        weekly = aggregate_weekly(bars_upto(bars_by_timeframe["1d"], cutoff))
        indicators["1w"] = indicator_snapshot(weekly, timeframe="1w")
    return {
        "instrument": instrument,
        "as_of": cutoff.isoformat(),
        "indicators": indicators,
        "funding": "unknown",
        "open_interest": "unknown",
        "liquidations": "unknown",
        "tvl": "unknown",
        "token_unlocks": "unknown",
    }
