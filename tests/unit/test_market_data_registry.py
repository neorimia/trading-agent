"""MarketDataAdapterRegistry — dispatch pe execution_venue, fără swallow silențios."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.data.market_data_registry import MarketDataAdapterRegistry, MarketDataUnavailable
from src.data.sources import Bar

START = datetime(2026, 9, 1, tzinfo=timezone.utc)
END = datetime(2026, 9, 2, tzinfo=timezone.utc)


class _FakeKrakenSource:
    closed = False

    def fetch_bars(self, instrument, start, end, timeframe):
        return [
            Bar(
                instrument=instrument,
                timestamp=end,
                open=Decimal("1"),
                high=Decimal("1"),
                low=Decimal("1"),
                close=Decimal("1"),
                volume=Decimal("1"),
            )
        ]

    def close(self) -> None:
        self.closed = True


def test_dispatches_to_registered_adapter_for_executable_instrument() -> None:
    registry = MarketDataAdapterRegistry(adapters={"KRAKEN": _FakeKrakenSource})
    bars = registry.fetch_bars("ETHUSD", START, END, "1d")
    assert bars[0].instrument == "ETHUSD"


def test_research_only_instrument_raises_typed_error_not_empty_list() -> None:
    registry = MarketDataAdapterRegistry(adapters={"KRAKEN": _FakeKrakenSource})
    with pytest.raises(MarketDataUnavailable) as excinfo:
        registry.fetch_bars("AAPL", START, END, "1d")
    assert excinfo.value.reason == "research_only"
    assert excinfo.value.instrument == "AAPL"


def test_missing_adapter_for_execution_venue_raises_typed_error() -> None:
    registry = MarketDataAdapterRegistry(adapters={})
    with pytest.raises(MarketDataUnavailable) as excinfo:
        registry.fetch_bars("ETHUSD", START, END, "1d")
    assert excinfo.value.reason == "no_adapter"


def test_source_is_closed_after_fetch() -> None:
    source = _FakeKrakenSource()
    registry = MarketDataAdapterRegistry(adapters={"KRAKEN": lambda: source})
    registry.fetch_bars("BTCUSD", START, END, "1d")
    assert source.closed is True
