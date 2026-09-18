"""MarketDataCache: persistă barele și întoarce același hash la re-citire."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.data.cache import MarketDataCache, canonical_dataset_hash
from src.data.sources import CsvBarDataSource

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "bars_ethusd_1d.csv"


def test_get_or_fetch_writes_cache_and_is_stable(tmp_path: Path) -> None:
    start = datetime(2024, 11, 1, tzinfo=timezone.utc)
    end = datetime(2024, 12, 16, tzinfo=timezone.utc)
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    cache = MarketDataCache(tmp_path / "market_data", CsvBarDataSource(FIXTURE))
    bars_1, hash_1 = cache.get_or_fetch("ETHUSD", start, end, "1d", now=now)
    bars_2, hash_2 = cache.get_or_fetch("ETHUSD", start, end, "1d", now=now)
    assert hash_1 == hash_2
    assert hash_1 == canonical_dataset_hash(bars_1)
    assert len(hash_1) == 64
    assert [bar.timestamp for bar in bars_1] == [bar.timestamp for bar in bars_2]
    assert list(tmp_path.joinpath("market_data").glob("*.json"))


def test_hash_changes_when_a_close_changes(tmp_path: Path) -> None:
    start = datetime(2024, 11, 1, tzinfo=timezone.utc)
    end = datetime(2024, 12, 16, tzinfo=timezone.utc)
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    cache = MarketDataCache(tmp_path / "market_data", CsvBarDataSource(FIXTURE))
    bars, digest = cache.get_or_fetch("ETHUSD", start, end, "1d", now=now)
    mutated = list(bars)
    first = mutated[0]
    mutated[0] = type(first)(
        instrument=first.instrument,
        timestamp=first.timestamp,
        open=first.open,
        high=first.high,
        low=first.low,
        close=first.close + 1,
        volume=first.volume,
    )
    assert canonical_dataset_hash(mutated) != digest
