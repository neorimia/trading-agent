"""Clasificator de regim de piață — pur, fără look-ahead, folosit ca filtru de strategii
și pentru sliced-reporting în backtest (`src/engine/metrics.py`).

Nu e o strategie: nu produce BUY/SELL, doar context (trend/range, bull/bear/sideways,
volatilitate, volum, șoc) pe care strategiile îl citesc sau pe care rapoartele de
backtest îl folosesc pentru a arăta unde funcționează/eșuează o strategie.
`bars` trebuie deja tăiate de apelant la T — funcțiile de mai jos nu se uită niciodată
înainte de ultimul element din lista primită.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from src.data.sources import Bar
from src.engine.indicators import adx, atr, volume_zscore

MarketRegime = Literal["trend", "range", "unknown"]
Direction = Literal["bull", "bear", "sideways", "unknown"]
VolBucket = Literal["high", "low", "normal", "unknown"]
VolumeBucket = Literal["high", "low", "normal", "unknown"]

DEFAULT_ADX_PERIOD = 14
DEFAULT_TREND_THRESHOLD = Decimal("25")
DEFAULT_DIRECTION_WINDOW = 20
DEFAULT_DIRECTION_THRESHOLD_PCT = Decimal("3")
DEFAULT_VOL_ATR_PERIOD = 14
DEFAULT_VOL_HIGH_PCT = Decimal("2.5")  # ATR/close (%) peste care volatilitatea e "high"
DEFAULT_VOL_LOW_PCT = Decimal("0.8")  # ATR/close (%) sub care volatilitatea e "low"
DEFAULT_VOLUME_LOOKBACK = 20
DEFAULT_VOLUME_Z_HIGH = Decimal("0.75")
DEFAULT_VOLUME_Z_LOW = Decimal("-0.75")
DEFAULT_SHOCK_ATR_MULT = Decimal("3")


def classify_regime(
    bars: list[Bar],
    *,
    adx_period: int = DEFAULT_ADX_PERIOD,
    trend_threshold: Decimal = DEFAULT_TREND_THRESHOLD,
) -> MarketRegime:
    """`trend` dacă ADX >= prag, `range` dacă ADX < prag, `unknown` dacă nu sunt destule bare.

    Aproximare deliberat simplă (un singur indicator). Nu distinge bull/bear în interiorul
    unui trend — asta se face separat, în `classify_direction`.
    """
    value = adx(bars, adx_period)
    if value is None:
        return "unknown"
    return "trend" if value >= trend_threshold else "range"


def classify_direction(
    bars: list[Bar],
    *,
    window: int = DEFAULT_DIRECTION_WINDOW,
    threshold_pct: Decimal = DEFAULT_DIRECTION_THRESHOLD_PCT,
) -> Direction:
    """`bull`/`bear` dacă randamentul simplu pe ultimele `window` bare depășește pragul,
    altfel `sideways`. Aproximare simplă (randament, nu regresie/pantă)."""
    if len(bars) < window + 1:
        return "unknown"
    slice_ = bars[-(window + 1) :]
    start, end = slice_[0].close, slice_[-1].close
    if start <= 0:
        return "unknown"
    change_pct = (end - start) / start * Decimal("100")
    if change_pct >= threshold_pct:
        return "bull"
    if change_pct <= -threshold_pct:
        return "bear"
    return "sideways"


def classify_volatility(
    bars: list[Bar],
    *,
    atr_period: int = DEFAULT_VOL_ATR_PERIOD,
    high_pct: Decimal = DEFAULT_VOL_HIGH_PCT,
    low_pct: Decimal = DEFAULT_VOL_LOW_PCT,
) -> VolBucket:
    """Bucket pe baza ATR normalizat de close (ATR% pe bară). Prag fix, nu percentilă
    rulantă — simplu și reproductibil, dar nu adaptiv la instrument/timeframe."""
    value = atr(bars, atr_period)
    if value is None or not bars:
        return "unknown"
    close = bars[-1].close
    if close <= 0:
        return "unknown"
    atr_pct = value / close * Decimal("100")
    if atr_pct >= high_pct:
        return "high"
    if atr_pct <= low_pct:
        return "low"
    return "normal"


def classify_volume(
    bars: list[Bar],
    *,
    lookback: int = DEFAULT_VOLUME_LOOKBACK,
    high_z: Decimal = DEFAULT_VOLUME_Z_HIGH,
    low_z: Decimal = DEFAULT_VOLUME_Z_LOW,
) -> VolumeBucket:
    volumes = [bar.volume for bar in bars]
    z = volume_zscore(volumes, lookback)
    if z is None:
        return "unknown"
    if z >= high_z:
        return "high"
    if z <= low_z:
        return "low"
    return "normal"


def detect_shock(
    bars: list[Bar],
    *,
    atr_period: int = DEFAULT_VOL_ATR_PERIOD,
    atr_mult: Decimal = DEFAULT_SHOCK_ATR_MULT,
) -> bool:
    """`True` dacă mișcarea ultimei bare depășește `atr_mult` × ATR-ul barelor anterioare
    (ATR calculat FĂRĂ bara curentă, ca să nu se auto-includă în prag)."""
    if len(bars) < atr_period + 2:
        return False
    prior_atr = atr(bars[:-1], atr_period)
    if prior_atr is None or prior_atr == 0:
        return False
    last = bars[-1]
    move = abs(last.close - bars[-2].close)
    return move > atr_mult * prior_atr


@dataclass(frozen=True)
class RegimeTag:
    timestamp: datetime
    trend: MarketRegime
    direction: Direction
    volatility: VolBucket
    volume: VolumeBucket
    shock: bool


def tag_regimes(
    bars: list[Bar],
    *,
    trailing_window: int = 90,
    adx_period: int = DEFAULT_ADX_PERIOD,
    trend_threshold: Decimal = DEFAULT_TREND_THRESHOLD,
    direction_window: int = DEFAULT_DIRECTION_WINDOW,
    direction_threshold_pct: Decimal = DEFAULT_DIRECTION_THRESHOLD_PCT,
    vol_atr_period: int = DEFAULT_VOL_ATR_PERIOD,
    volume_lookback: int = DEFAULT_VOLUME_LOOKBACK,
) -> list[RegimeTag]:
    """Un tag per bară, folosind DOAR bare `<= t` (fereastră trunchiată la `trailing_window`
    pentru cost O(n × trailing_window) în loc de O(n²) — o fereastră mai mică de trecut tot
    nu vede viitorul, deci nu introduce look-ahead).
    """
    tags: list[RegimeTag] = []
    for index in range(len(bars)):
        window_start = max(0, index + 1 - trailing_window)
        window = bars[window_start : index + 1]
        tags.append(
            RegimeTag(
                timestamp=bars[index].timestamp,
                trend=classify_regime(
                    window, adx_period=adx_period, trend_threshold=trend_threshold
                ),
                direction=classify_direction(
                    window, window=direction_window, threshold_pct=direction_threshold_pct
                ),
                volatility=classify_volatility(window, atr_period=vol_atr_period),
                volume=classify_volume(window, lookback=volume_lookback),
                shock=detect_shock(window, atr_period=vol_atr_period),
            )
        )
    return tags
