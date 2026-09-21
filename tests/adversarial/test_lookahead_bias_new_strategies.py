"""Look-ahead bias pentru StrategySpec noi (EMA/Donchian/RSI): decizia la T nu poate
depinde de bare cu timestamp > T. Aceeași metodologie ca
`tests/adversarial/test_lookahead_bias.py`, aplicată interfeței comune.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.data.sources import Bar
from src.engine.strategies.donchian_breakout import DonchianBreakoutParams, DonchianBreakoutSpec
from src.engine.strategies.ema_cross import EmaTrendFilterParams, EmaTrendFilterSpec
from src.engine.strategies.rsi_mean_reversion import RsiMeanReversionParams, RsiMeanReversionSpec

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _bars(n: int) -> list[Bar]:
    bars = []
    price = Decimal("100")
    for i in range(n):
        step = Decimal("1") if i % 3 != 0 else Decimal("-0.6")
        price += step
        volume = Decimal("100") if i % 7 != 0 else Decimal("500")
        bars.append(
            Bar(
                instrument="ETHUSD",
                timestamp=START + timedelta(hours=i),
                open=price,
                high=price + Decimal("0.7"),
                low=price - Decimal("0.7"),
                close=price,
                volume=volume,
            )
        )
    return bars


def _mutate_after(bars: list[Bar], cutoff_index: int) -> list[Bar]:
    mutated: list[Bar] = []
    for index, bar in enumerate(bars):
        if index <= cutoff_index:
            mutated.append(bar)
            continue
        mutated.append(
            Bar(
                instrument=bar.instrument,
                timestamp=bar.timestamp,
                open=Decimal("999999"),
                high=Decimal("999999"),
                low=Decimal("999999"),
                close=Decimal("999999"),
                volume=Decimal("999999"),
            )
        )
    return mutated


_SPECS = [
    (
        "ema_cross",
        EmaTrendFilterSpec(
            id="ema", version=1, status="experimental", updated_at=START, params=EmaTrendFilterParams()
        ),
    ),
    (
        "donchian_breakout",
        DonchianBreakoutSpec(
            id="donchian",
            version=1,
            status="experimental",
            updated_at=START,
            params=DonchianBreakoutParams(),
        ),
    ),
    (
        "rsi_mean_reversion",
        RsiMeanReversionSpec(
            id="rsi",
            version=1,
            status="experimental",
            updated_at=START,
            params=RsiMeanReversionParams(),
        ),
    ),
]


def test_all_new_specs_ignore_future_bars() -> None:
    bars = _bars(80)
    for name, spec in _SPECS:
        for cutoff in (35, 50, 65, 79):
            clean = spec.evaluate(bars[: cutoff + 1])
            dirty = spec.evaluate(_mutate_after(bars, cutoff)[: cutoff + 1])
            assert clean == dirty, f"{name} leaked future data at cutoff={cutoff}"
