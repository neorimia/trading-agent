"""Fabrică de surse istorice: Kraken (aliniat la execuție) sau Binance (backfill lung)."""

from __future__ import annotations

from pathlib import Path

from src.data.cache import MarketDataCache
from src.data.kraken import KrakenPublicOHLCSource
from src.data.sources import BinanceKlinesSource, CsvBarDataSource, DataSource
from src.data.venue_registry import DEFAULT_HISTORICAL_SOURCE, HistoricalSource


def make_historical_source(
    source: HistoricalSource = DEFAULT_HISTORICAL_SOURCE,
    *,
    csv_path: str | Path | None = None,
) -> DataSource:
    if csv_path is not None:
        return CsvBarDataSource(csv_path)
    if source == "KRAKEN":
        return KrakenPublicOHLCSource()
    return BinanceKlinesSource()


def make_cached_historical(
    cache_dir: str | Path,
    source: HistoricalSource = DEFAULT_HISTORICAL_SOURCE,
    *,
    csv_path: str | Path | None = None,
) -> MarketDataCache:
    """Cache local peste orice DataSource — backtest comparabil cu live pe aceeași serie."""
    return MarketDataCache(cache_dir, make_historical_source(source, csv_path=csv_path))
