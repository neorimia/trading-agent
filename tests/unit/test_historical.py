"""MarketDataCache + Kraken DataSource (OHLC mock) — backtest aliniat la execuție."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.data.cache import MarketDataCache, canonical_dataset_hash
from src.data.historical import make_historical_source
from src.data.kraken import KrakenPublicOHLCSource
from src.data.sources import CsvBarDataSource
from src.data.venue_registry import DEFAULT_HISTORICAL_SOURCE


def test_default_historical_source_is_binance_backfill() -> None:
    assert DEFAULT_HISTORICAL_SOURCE == "BINANCE"
    source = make_historical_source("BINANCE")
    assert source.__class__.__name__ == "BinanceKlinesSource"
    assert make_historical_source("KRAKEN").__class__.__name__ == "KrakenPublicOHLCSource"


def test_kraken_source_is_cacheable(tmp_path: Path) -> None:
    open_ts = int(datetime(2024, 11, 1, tzinfo=timezone.utc).timestamp())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "error": [],
                "result": {
                    "XETHZUSD": [
                        [open_ts, "2500.0", "2550.0", "2480.0", "2520.0", "2510.0", "100.5", 12]
                    ],
                    "last": open_ts,
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    cache = MarketDataCache(tmp_path / "md", KrakenPublicOHLCSource(http_client=client))
    start = datetime(2024, 11, 1, tzinfo=timezone.utc)
    end = datetime(2024, 11, 2, tzinfo=timezone.utc)
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    bars_1, hash_1 = cache.get_or_fetch("ETHUSD", start, end, "1d", now=now)
    bars_2, hash_2 = cache.get_or_fetch("ETHUSD", start, end, "1d", now=now)
    assert hash_1 == hash_2 == canonical_dataset_hash(bars_1)
    assert len(bars_1) == 1
    assert bars_1[0].instrument == "ETHUSD"


def test_csv_factory(tmp_path: Path) -> None:
    fixture = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "bars_ethusd_1d.csv"
    source = make_historical_source(csv_path=fixture)
    assert isinstance(source, CsvBarDataSource)
