"""Dispatch adapter de date de piață pe `execution_venue`. Zero swallow silențios.

Instrumente fără venue de execuție (echities research-only) sau fără adapter
înregistrat eșuează cu `MarketDataUnavailable`, tipat pe `reason` — niciodată
`except Exception: bars = []` fără urmă.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Literal

from src.data.kraken import KrakenPublicOHLCSource
from src.data.sources import Bar, DataSource
from src.data.venue_registry import ExecutionVenue, get_instrument

MarketDataUnavailableReason = Literal["research_only", "no_adapter"]


class MarketDataUnavailable(RuntimeError):
    """Nu există o sursă de date executabilă pentru instrument."""

    def __init__(self, instrument: str, reason: MarketDataUnavailableReason) -> None:
        self.instrument = instrument
        self.reason = reason
        super().__init__(f"{reason}: {instrument}")


_DEFAULT_ADAPTER_FACTORIES: dict[ExecutionVenue, Callable[[], DataSource]] = {
    "KRAKEN": KrakenPublicOHLCSource,
}


class MarketDataAdapterRegistry:
    """Dispatch pe `VenueInstrument.execution_venue`, per apel (adaptere fără stare partajată)."""

    def __init__(
        self,
        adapters: dict[ExecutionVenue, Callable[[], DataSource]] | None = None,
    ) -> None:
        self._adapters = dict(adapters) if adapters is not None else dict(_DEFAULT_ADAPTER_FACTORIES)

    def fetch_bars(
        self, instrument: str, start: datetime, end: datetime, timeframe: str
    ) -> list[Bar]:
        spec = get_instrument(instrument)
        if spec.execution_venue == "NONE":
            raise MarketDataUnavailable(instrument, "research_only")
        factory = self._adapters.get(spec.execution_venue)
        if factory is None:
            raise MarketDataUnavailable(instrument, "no_adapter")
        source = factory()
        try:
            return source.fetch_bars(instrument, start, end, timeframe)
        finally:
            close = getattr(source, "close", None)
            if callable(close):
                close()
