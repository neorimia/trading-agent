"""Fabrică de surse istorice: Kraken (aliniat la execuție) sau Binance (backfill lung)."""

from __future__ import annotations

from pathlib import Path

from src.data.kraken import KrakenPublicOHLCSource
from src.data.market_data_repository import MarketDataRepository, open_market_data_cache
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


def default_market_data_source_name(
    source: HistoricalSource = DEFAULT_HISTORICAL_SOURCE,
    *,
    csv_path: str | Path | None = None,
) -> str:
    """Maps a `DataSource` choice to its `market_data_sources.name` row (seeded by
    `scripts/db/seed.py`) — used when the postgres backend is selected without an
    explicit `source_name`."""
    if csv_path is not None:
        return "csv_fixture"
    return "kraken_public_ohlc" if source == "KRAKEN" else "binance_public_klines"


def make_cached_historical(
    cache_dir: str | Path,
    source: HistoricalSource = DEFAULT_HISTORICAL_SOURCE,
    *,
    csv_path: str | Path | None = None,
    backend: str = "files",
    database_url: str | None = None,
    source_name: str | None = None,
) -> MarketDataRepository:
    """Cache peste orice DataSource — backtest comparabil cu live pe aceeași serie.

    `backend='files'` (implicit, rollback target) scrie JSON per fereastră sub
    `.cache/market_data/`. `backend='postgres'` citește/scrie hypertable-ul
    `ohlcv_candles` (`MARKET_DATA_STORE_BACKEND`, docs/database-cutover-playbook.md
    §Market data) — cere `database_url` (rol `market_data_writer`).
    """
    return open_market_data_cache(
        backend=backend,
        cache_dir=cache_dir,
        source=make_historical_source(source, csv_path=csv_path),
        database_url=database_url,
        source_name=source_name or default_market_data_source_name(source, csv_path=csv_path),
    )
