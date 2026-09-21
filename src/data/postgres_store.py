"""PostgreSQL implementation of the market data cache (hypertable `ohlcv_candles`).

Mirrors `src/data/cache.py` (`MarketDataCache`) so callers (`make_cached_historical`,
`get_or_fetch`) do not care which backend is active — see
`src/data/market_data_repository.py` for the `files`/`postgres` switch
(`MARKET_DATA_STORE_BACKEND`, docs/database-cutover-playbook.md §Market data).

`Bar.timestamp` is close-time (lookahead-safe: the bar is known at close, see
`src/data/sources.py`). `ohlcv_candles.open_time` is period start. All sources in
this codebase (Kraken, Binance, the CSV fixture) share the same convention:
`close_time = open_time + timeframe_delta - 1s` (see `src/data/kraken.py`), so the
conversion is exact, not an approximation.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from src.data.cache import canonical_dataset_hash
from src.data.sources import Bar, DataSource, require_utc, timeframe_delta
from src.data.validation import DataValidator, ValidationReport
from src.db.pool import get_database_pool

_ONE_SECOND = timedelta(seconds=1)


def _open_time(close_time: datetime, delta: timedelta) -> datetime:
    return close_time - delta + _ONE_SECOND


def _close_time(open_time: datetime, delta: timedelta) -> datetime:
    return open_time + delta - _ONE_SECOND


def _format_report(report: ValidationReport) -> str:
    details = "; ".join(f"{issue.code}: {issue.message}" for issue in report.issues)
    return f"market data validation failed: {details}"


class PostgresCandleStore:
    """Resolves instrument/source ids and reads/writes `ohlcv_candles` rows."""

    def __init__(self, database_url: str) -> None:
        self._pool = get_database_pool(database_url)

    def close(self) -> None:
        """Pool lifetime belongs to the process, not an individual request."""

    @staticmethod
    def _instrument_id(connection: Any, canonical_symbol: str) -> Any:
        row = connection.execute(
            "SELECT instrument_id FROM instruments WHERE canonical_symbol = %s",
            (canonical_symbol,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown instrument symbol {canonical_symbol!r}")
        return row["instrument_id"]

    @staticmethod
    def _source_id(connection: Any, source_name: str) -> int:
        row = connection.execute(
            "SELECT source_id FROM market_data_sources WHERE name = %s",
            (source_name,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown market data source {source_name!r}")
        return row["source_id"]

    def upsert_bars(
        self,
        instrument: str,
        source_name: str,
        timeframe: str,
        bars: list[Bar],
    ) -> int:
        """UPSERT on the primary key — re-ingesting the same window updates in place,
        never duplicates (docs/database-design.md §13)."""
        if not bars:
            return 0
        delta = timeframe_delta(timeframe)
        written = 0
        with self._pool.connection() as connection:
            with connection.transaction():
                instrument_id = self._instrument_id(connection, instrument)
                source_id = self._source_id(connection, source_name)
                for bar in bars:
                    open_time = _open_time(require_utc(bar.timestamp, "timestamp"), delta)
                    connection.execute(
                        """
                        INSERT INTO ohlcv_candles (
                            source_id, instrument_id, timeframe, open_time,
                            open, high, low, close, volume, is_final
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, true)
                        ON CONFLICT (source_id, instrument_id, timeframe, open_time)
                        DO UPDATE SET
                            open = EXCLUDED.open,
                            high = EXCLUDED.high,
                            low = EXCLUDED.low,
                            close = EXCLUDED.close,
                            volume = EXCLUDED.volume,
                            is_final = true,
                            updated_at = now()
                        """,
                        (
                            source_id,
                            instrument_id,
                            timeframe,
                            open_time,
                            bar.open,
                            bar.high,
                            bar.low,
                            bar.close,
                            bar.volume,
                        ),
                    )
                    written += 1
        return written

    def load_bars(
        self,
        instrument: str,
        source_name: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Bar]:
        delta = timeframe_delta(timeframe)
        start_open = _open_time(require_utc(start, "start"), delta)
        end_open = _open_time(require_utc(end, "end"), delta)
        with self._pool.connection() as connection:
            instrument_id = self._instrument_id(connection, instrument)
            source_id = self._source_id(connection, source_name)
            rows = connection.execute(
                """
                SELECT open_time, open, high, low, close, volume
                FROM ohlcv_candles
                WHERE source_id = %s AND instrument_id = %s AND timeframe = %s
                  AND open_time >= %s AND open_time <= %s
                ORDER BY open_time
                """,
                (source_id, instrument_id, timeframe, start_open, end_open),
            ).fetchall()
        return [
            Bar(
                instrument=instrument,
                timestamp=_close_time(row["open_time"], delta),
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )
            for row in rows
        ]

    def has_full_coverage(
        self,
        instrument: str,
        source_name: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> bool:
        """True when the window already has as many candles as expected close-times.

        A coarse but safe gate: it only short-circuits the network fetch when the
        count matches; any mismatch (gap, never-fetched window) falls through to a
        real `fetch_bars` call rather than silently returning a partial series.
        """
        delta = timeframe_delta(timeframe)
        start_utc = require_utc(start, "start")
        end_utc = require_utc(end, "end")
        if end_utc <= start_utc:
            raise ValueError("end must be after start")
        expected = 0
        cursor = start_utc
        while cursor <= end_utc:
            expected += 1
            cursor += delta
        start_open = _open_time(start_utc, delta)
        end_open = _open_time(end_utc, delta)
        with self._pool.connection() as connection:
            try:
                instrument_id = self._instrument_id(connection, instrument)
                source_id = self._source_id(connection, source_name)
            except ValueError:
                return False
            row = connection.execute(
                """
                SELECT count(*) AS count FROM ohlcv_candles
                WHERE source_id = %s AND instrument_id = %s AND timeframe = %s
                  AND open_time >= %s AND open_time <= %s
                """,
                (source_id, instrument_id, timeframe, start_open, end_open),
            ).fetchone()
        return bool(row) and row["count"] >= expected


class PostgresMarketDataCache:
    """Same `get_or_fetch(instrument, start, end, timeframe, *, now=None)` contract as
    `MarketDataCache` (src/data/cache.py), backed by `ohlcv_candles` instead of JSON
    files under `.cache/market_data/`."""

    def __init__(self, database_url: str, source: DataSource, *, source_name: str) -> None:
        self._store = PostgresCandleStore(database_url)
        self._source = source
        self._source_name = source_name
        self._validator = DataValidator()

    def close(self) -> None:
        self._store.close()

    def get_or_fetch(
        self,
        instrument: str,
        start: datetime,
        end: datetime,
        timeframe: str,
        *,
        now: datetime | None = None,
    ) -> tuple[list[Bar], str]:
        if self._store.has_full_coverage(instrument, self._source_name, timeframe, start, end):
            bars = self._store.load_bars(instrument, self._source_name, timeframe, start, end)
        else:
            bars = self._source.fetch_bars(instrument, start, end, timeframe)
            report = self._validator.validate(bars, timeframe, now=now)
            if not report.ok:
                raise ValueError(_format_report(report))
            self._store.upsert_bars(instrument, self._source_name, timeframe, bars)
            bars = self._store.load_bars(instrument, self._source_name, timeframe, start, end)
        dataset_hash = canonical_dataset_hash(bars)
        report = self._validator.validate(bars, timeframe, now=now)
        if not report.ok:
            raise ValueError(_format_report(report))
        return bars, dataset_hash
