"""PostgreSQL market data store: constraints, idempotence, hash parity, role isolation,
hypertable, and importer reconciliation."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pytest

from scripts.db.import_market_data import import_market_data
from scripts.db.seed import seed_reference_data
from src.data.cache import MarketDataCache, canonical_dataset_hash
from src.data.postgres_store import PostgresCandleStore, PostgresMarketDataCache
from src.data.sources import CsvBarDataSource
from src.db.pool import close_database_pools

pytestmark = pytest.mark.postgres
REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_CSV = REPO_ROOT / "tests" / "fixtures" / "bars_ethusd_1d.csv"
START = datetime(2024, 11, 1, tzinfo=timezone.utc)
END = datetime(2024, 11, 10, 23, 59, 59, tzinfo=timezone.utc)
NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _admin_database_url() -> str:
    """The migration-owner role, for schema setup/seeding/role-isolation baselines."""
    value = os.environ.get("ADMIN_DATABASE_URL") or os.environ.get("MIGRATION_DATABASE_URL")
    if not value:
        pytest.skip("ADMIN_DATABASE_URL is not configured")
    return value


def _market_data_database_url() -> str:
    """The market_data_writer application role, as production code paths use it."""
    value = os.environ.get("MARKET_DATA_DATABASE_URL")
    if not value:
        pytest.skip("MARKET_DATA_DATABASE_URL is not configured")
    return value


def _control_database_url() -> str:
    value = os.environ.get("CONTROL_DATABASE_URL")
    if not value:
        pytest.skip("CONTROL_DATABASE_URL is not configured")
    return value


def _research_database_url() -> str:
    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        pytest.skip("TEST_DATABASE_URL is not configured")
    return value


@pytest.fixture(autouse=True)
def clean_database() -> None:
    url = _admin_database_url()
    close_database_pools()
    with psycopg.connect(url) as connection:
        connection.execute("TRUNCATE ohlcv_candles")
        # Reference tables (instruments/market_data_sources) are UPSERTed, never
        # truncated — matches tests/integration/test_postgres_research.py.
        seed_reference_data(
            connection,
            universe_path=REPO_ROOT / "config/universe.yaml",
            sources_path=REPO_ROOT / "config/research_sources.yaml",
        )
    yield
    close_database_pools()


def _ids(connection: psycopg.Connection) -> tuple[str, int]:
    instrument = connection.execute(
        "SELECT instrument_id FROM instruments WHERE canonical_symbol = 'ETHUSD'"
    ).fetchone()
    source = connection.execute(
        "SELECT source_id FROM market_data_sources WHERE name = 'kraken_public_ohlc'"
    ).fetchone()
    assert instrument is not None and source is not None
    return instrument[0], source[0]


def test_upsert_then_reupsert_is_idempotent_same_pk_count() -> None:
    bars = CsvBarDataSource(FIXTURE_CSV).fetch_bars("ETHUSD", START, END, "1d")
    store = PostgresCandleStore(_market_data_database_url())
    first_written = store.upsert_bars("ETHUSD", "kraken_public_ohlc", "1d", bars)
    second_written = store.upsert_bars("ETHUSD", "kraken_public_ohlc", "1d", bars)
    assert first_written == second_written == len(bars)
    loaded = store.load_bars("ETHUSD", "kraken_public_ohlc", "1d", START, END)
    assert len(loaded) == len(bars)


def test_duplicate_insert_without_on_conflict_is_rejected() -> None:
    with psycopg.connect(_admin_database_url()) as connection:
        instrument_id, source_id = _ids(connection)
        connection.execute(
            """
            INSERT INTO ohlcv_candles (
                source_id, instrument_id, timeframe, open_time, open, high, low, close, volume
            ) VALUES (%s, %s, '1d', %s, 1, 1, 1, 1, 1)
            """,
            (source_id, instrument_id, START),
        )
        with pytest.raises(psycopg.errors.UniqueViolation):
            connection.execute(
                """
                INSERT INTO ohlcv_candles (
                    source_id, instrument_id, timeframe, open_time,
                    open, high, low, close, volume
                ) VALUES (%s, %s, '1d', %s, 2, 2, 2, 2, 2)
                """,
                (source_id, instrument_id, START),
            )


def test_close_time_open_time_roundtrip_preserves_canonical_hash() -> None:
    bars = CsvBarDataSource(FIXTURE_CSV).fetch_bars("ETHUSD", START, END, "1d")
    original_hash = canonical_dataset_hash(bars)
    store = PostgresCandleStore(_market_data_database_url())
    store.upsert_bars("ETHUSD", "kraken_public_ohlc", "1d", bars)
    loaded = store.load_bars("ETHUSD", "kraken_public_ohlc", "1d", START, END)
    assert [bar.timestamp for bar in loaded] == [bar.timestamp for bar in bars]
    assert canonical_dataset_hash(loaded) == original_hash


def test_file_cache_and_postgres_store_produce_identical_hash(tmp_path: Path) -> None:
    file_cache = MarketDataCache(tmp_path, CsvBarDataSource(FIXTURE_CSV))
    file_bars, file_hash = file_cache.get_or_fetch("ETHUSD", START, END, "1d", now=NOW)

    pg_cache = PostgresMarketDataCache(
        _market_data_database_url(),
        CsvBarDataSource(FIXTURE_CSV),
        source_name="kraken_public_ohlc",
    )
    pg_bars, pg_hash = pg_cache.get_or_fetch("ETHUSD", START, END, "1d", now=NOW)

    assert file_hash == canonical_dataset_hash(file_bars)
    assert pg_hash == file_hash
    assert len(pg_bars) == len(file_bars)


def test_market_data_writer_can_write_candles_but_not_research_documents() -> None:
    with psycopg.connect(_market_data_database_url()) as connection:
        instrument_id, source_id = _ids(connection)
        connection.execute(
            """
            INSERT INTO ohlcv_candles (
                source_id, instrument_id, timeframe, open_time, open, high, low, close, volume
            ) VALUES (%s, %s, '1d', %s, 1, 1, 1, 1, 1)
            ON CONFLICT (source_id, instrument_id, timeframe, open_time)
            DO UPDATE SET open = EXCLUDED.open
            """,
            (source_id, instrument_id, START),
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("INSERT INTO research_documents (doc_id) VALUES ('x')")


def test_control_reader_can_read_candles_but_cannot_insert() -> None:
    with psycopg.connect(_admin_database_url()) as connection:
        instrument_id, source_id = _ids(connection)
        connection.execute(
            """
            INSERT INTO ohlcv_candles (
                source_id, instrument_id, timeframe, open_time, open, high, low, close, volume
            ) VALUES (%s, %s, '1d', %s, 1, 1, 1, 1, 1)
            """,
            (source_id, instrument_id, START),
        )
    with psycopg.connect(_control_database_url()) as connection:
        count = connection.execute("SELECT count(*) FROM ohlcv_candles").fetchone()[0]
        assert count == 1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("INSERT INTO ohlcv_candles (source_id) VALUES (1)")


def test_research_writer_cannot_insert_candles() -> None:
    with psycopg.connect(_research_database_url()) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("INSERT INTO ohlcv_candles (source_id) VALUES (1)")


def test_ohlcv_candles_and_siblings_are_hypertables() -> None:
    with psycopg.connect(_admin_database_url()) as connection:
        rows = {
            row[0]
            for row in connection.execute(
                "SELECT hypertable_name FROM timescaledb_information.hypertables"
            ).fetchall()
        }
    assert {"ohlcv_candles", "order_book_snapshots", "trades"} <= rows


def test_importer_from_cache_dry_run_flags_incomplete_provenance(tmp_path: Path) -> None:
    cache = MarketDataCache(tmp_path, CsvBarDataSource(FIXTURE_CSV))
    cache.get_or_fetch("ETHUSD", START, END, "1d", now=NOW)

    report = import_market_data(
        database_url=_admin_database_url(),
        universe_path=REPO_ROOT / "config/universe.yaml",
        research_sources_path=REPO_ROOT / "config/research_sources.yaml",
        instruments=["ETHUSD"],
        timeframe="1d",
        start=START,
        end=END,
        source="KRAKEN",
        cache_dir=tmp_path,
        dry_run=True,
    )
    assert report["provenance_incomplete"] is True
    entry = report["instruments"]["ETHUSD"]
    assert entry["used_cache"] is True
    assert entry["written"] == 0
    assert entry["source_window_count"] == entry["destination_count"] > 0
    assert entry["rejected_bar_count"] == 0
    assert entry["gaps"] == []
    assert "error" not in entry


def test_importer_rerun_on_cached_fixture_is_idempotent(tmp_path: Path) -> None:
    cache = MarketDataCache(tmp_path, CsvBarDataSource(FIXTURE_CSV))
    cache.get_or_fetch("ETHUSD", START, END, "1d", now=NOW)

    kwargs: dict = {
        "database_url": _admin_database_url(),
        "universe_path": REPO_ROOT / "config/universe.yaml",
        "research_sources_path": REPO_ROOT / "config/research_sources.yaml",
        "instruments": ["ETHUSD"],
        "timeframe": "1d",
        "start": START,
        "end": END,
        "source": "KRAKEN",
        "cache_dir": tmp_path,
        "dry_run": False,
    }
    first = import_market_data(**kwargs)
    second = import_market_data(**kwargs)

    first_entry = first["instruments"]["ETHUSD"]
    second_entry = second["instruments"]["ETHUSD"]
    assert "error" not in first_entry and "error" not in second_entry
    assert first_entry["destination_count"] == second_entry["destination_count"]
    assert first_entry["canonical_dataset_hash"] == second_entry["canonical_dataset_hash"]
    assert first_entry["natural_key_conflicts"] == 0
    assert second_entry["natural_key_conflicts"] == 0
    assert first_entry["gaps"] == second_entry["gaps"] == []


def test_importer_missing_cache_window_is_skipped_not_guessed(tmp_path: Path) -> None:
    report = import_market_data(
        database_url=_admin_database_url(),
        universe_path=REPO_ROOT / "config/universe.yaml",
        research_sources_path=REPO_ROOT / "config/research_sources.yaml",
        instruments=["ETHUSD"],
        timeframe="1d",
        start=START,
        end=END,
        source="KRAKEN",
        cache_dir=tmp_path,
        dry_run=True,
    )
    assert report["provenance_incomplete"] is True
    entry = report["instruments"]["ETHUSD"]
    assert entry["destination_count"] is None
    assert "error" in entry
