"""Look-ahead bias: decizia la T nu depinde de barele cu timestamp > T.

Metodologie inspirată de Freqtrade lookahead analysis, fără dependență de cod Freqtrade.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from src.data.sources import Bar, CsvBarDataSource
from src.engine.signals import baseline_proposal, market_summary_from_bars, proposal_context_at

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "bars_ethusd_1d.csv"
FAST = 10
SLOW = 20
LOOKBACK = 20


def _load() -> list[Bar]:
    return CsvBarDataSource(FIXTURE).fetch_bars(
        "ETHUSD",
        datetime(2024, 11, 1, tzinfo=timezone.utc),
        datetime(2024, 12, 16, tzinfo=timezone.utc),
        "1d",
    )


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
                open=Decimal("99999"),
                high=Decimal("99999"),
                low=Decimal("99999"),
                close=Decimal("99999"),
                volume=Decimal("1"),
            )
        )
    return mutated


def test_baseline_decision_at_t_ignores_future_bars() -> None:
    bars = _load()
    for cutoff in (19, 24, 30, 40):
        truncated = bars[: cutoff + 1]
        poisoned = _mutate_after(bars, cutoff)[: cutoff + 1]
        assert truncated == poisoned
        left = baseline_proposal(truncated, fast_period=FAST, slow_period=SLOW)
        right = baseline_proposal(
            _mutate_after(bars, cutoff)[: cutoff + 1],
            fast_period=FAST,
            slow_period=SLOW,
        )
        assert left == right


def test_market_summary_does_not_contain_future_prices() -> None:
    bars = _load()
    cutoff = 25
    poisoned_full = _mutate_after(bars, cutoff)
    summary = market_summary_from_bars(
        poisoned_full[: cutoff + 1],
        fast_period=FAST,
        slow_period=SLOW,
        lookback=LOOKBACK,
    )
    assert "99999" not in summary
    future_close = format(poisoned_full[-1].close, "f")
    assert future_close not in summary


def test_proposal_context_stable_when_future_is_corrupted() -> None:
    bars = _load()
    for cutoff in (20, 28, 35):
        clean = proposal_context_at(
            bars[: cutoff + 1],
            fast_period=FAST,
            slow_period=SLOW,
            lookback=LOOKBACK,
        )
        dirty = proposal_context_at(
            _mutate_after(bars, cutoff)[: cutoff + 1],
            fast_period=FAST,
            slow_period=SLOW,
            lookback=LOOKBACK,
        )
        assert clean == dirty
        assert clean.as_of == bars[cutoff].timestamp
