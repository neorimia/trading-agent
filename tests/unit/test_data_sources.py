"""DataSource: CSV local + Binance mapping. Fără rețea în testele default."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from src.data.sources import BinanceKlinesSource, CsvBarDataSource, UNIVERSE_TO_BINANCE

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "bars_ethusd_1d.csv"


def _window() -> tuple[datetime, datetime]:
    return (
        datetime(2024, 11, 1, tzinfo=timezone.utc),
        datetime(2024, 12, 16, tzinfo=timezone.utc),
    )


def test_csv_source_loads_ethusd_fixture() -> None:
    start, end = _window()
    bars = CsvBarDataSource(FIXTURE).fetch_bars("ETHUSD", start, end, "1d")
    assert len(bars) == 45
    assert bars[0].instrument == "ETHUSD"
    assert bars[0].close == Decimal("2510.00")
    assert bars[0].timestamp == datetime(2024, 11, 1, 23, 59, 59, tzinfo=timezone.utc)
    assert bars[-1].close == Decimal("2518.00")
    timestamps = [bar.timestamp for bar in bars]
    assert timestamps == sorted(timestamps)


def test_csv_source_filters_by_start_end() -> None:
    start = datetime(2024, 11, 10, tzinfo=timezone.utc)
    end = datetime(2024, 11, 12, 23, 59, 59, tzinfo=timezone.utc)
    bars = CsvBarDataSource(FIXTURE).fetch_bars("ETHUSD", start, end, "1d")
    assert [bar.timestamp.day for bar in bars] == [10, 11, 12]


def test_csv_source_rejects_naive_bounds(tmp_path: Path) -> None:
    source = CsvBarDataSource(FIXTURE)
    with pytest.raises(ValueError, match="timezone-aware"):
        source.fetch_bars(
            "ETHUSD",
            datetime(2024, 11, 1),
            datetime(2024, 12, 1, tzinfo=timezone.utc),
            "1d",
        )


def test_csv_source_rejects_bad_header(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("time,open,high,low,close,volume\n", encoding="utf-8")
    with pytest.raises(ValueError, match="header"):
        CsvBarDataSource(path).fetch_bars(
            "ETHUSD",
            datetime(2024, 11, 1, tzinfo=timezone.utc),
            datetime(2024, 12, 1, tzinfo=timezone.utc),
            "1d",
        )


def test_binance_source_paginates_and_maps_universe_symbol() -> None:
    calls: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        start_time = int(request.url.params["startTime"])
        if start_time == 0:
            rows = [
                [
                    0,
                    "100",
                    "110",
                    "90",
                    "105",
                    "10",
                    86_399_000,
                    "0",
                    1,
                    "0",
                    "0",
                    "0",
                ]
            ]
            return httpx.Response(200, json=rows)
        return httpx.Response(200, json=[])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    source = BinanceKlinesSource(http_client=client, base_url="https://api.binance.com/api/v3/klines")
    bars = source.fetch_bars(
        "ETHUSD",
        datetime(1970, 1, 1, tzinfo=timezone.utc),
        datetime(1970, 1, 2, tzinfo=timezone.utc),
        "1d",
    )
    assert UNIVERSE_TO_BINANCE["ETHUSD"] == "ETHUSDT"
    assert "symbol=ETHUSDT" in str(calls[0])
    assert "interval=1d" in str(calls[0])
    assert len(bars) == 1
    assert bars[0].instrument == "ETHUSD"
    assert bars[0].close == Decimal("105")


def test_binance_source_rejects_unmapped_instrument() -> None:
    source = BinanceKlinesSource(http_client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    with pytest.raises(ValueError, match="no Binance mapping"):
        source.fetch_bars(
            "AAPL",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            "1d",
        )


def _binance_reachable() -> bool:
    try:
        response = httpx.get("https://api.binance.com/api/v3/ping", timeout=3.0)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


@pytest.mark.network_live
def test_binance_live_fetch_few_daily_bars() -> None:
    if not _binance_reachable():
        pytest.skip("Binance public API is not reachable")
    source = BinanceKlinesSource()
    try:
        bars = source.fetch_bars(
            "ETHUSD",
            datetime(2024, 11, 1, tzinfo=timezone.utc),
            datetime(2024, 11, 5, 23, 59, 59, tzinfo=timezone.utc),
            "1d",
        )
    finally:
        source.close()
    assert len(bars) >= 4
    assert bars[0].instrument == "ETHUSD"
    assert bars[0].close > 0
