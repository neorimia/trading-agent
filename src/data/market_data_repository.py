"""Market data cache persistence boundary and backend selection.

Mirrors `src/research/repository.py` (`open_research_repository`) for the same
reversible-cutover shape: a `backend` string selects `files` (JSON windows on disk,
`src/data/cache.py`) or `postgres` (`ohlcv_candles` hypertable,
`src/data/postgres_store.py`). Default is `files` — the rollback target
(docs/database-cutover-playbook.md §Market data).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from src.data.cache import MarketDataCache
from src.data.sources import Bar, DataSource
from src.db.config import require_database_url


class MarketDataRepository(Protocol):
    def close(self) -> None: ...

    def get_or_fetch(
        self,
        instrument: str,
        start,
        end,
        timeframe: str,
        *,
        now=None,
    ) -> tuple[list[Bar], str]: ...


def open_market_data_cache(
    *,
    backend: str,
    cache_dir: str | Path,
    source: DataSource,
    database_url: str | None,
    source_name: str,
) -> MarketDataRepository:
    normalized = backend.strip().lower()
    if normalized == "files":
        return MarketDataCache(cache_dir, source)
    if normalized == "postgres":
        from src.data.postgres_store import PostgresMarketDataCache

        url = require_database_url(database_url, variable="MARKET_DATA_DATABASE_URL")
        return PostgresMarketDataCache(url, source, source_name=source_name)
    raise ValueError("MARKET_DATA_STORE_BACKEND must be 'files' or 'postgres'")
