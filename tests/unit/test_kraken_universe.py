"""KrakenAssetUniverseProvider — mock HTTP, zero apel de rețea real (pattern test_kraken_public.py)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import httpx

from src.discovery.crypto.kraken_universe import KrakenAssetUniverseProvider

_ASSET_PAIRS_PAYLOAD = {
    "error": [],
    "result": {
        "XETHZUSD": {"altname": "ETHUSD", "base": "XETH", "quote": "ZUSD", "status": "online", "ordermin": "0.01", "costmin": "0.5"},
        # Kraken raportează altname-ul canonic ca "XBTUSD" (nu "BTCUSD") pentru BTC/USD.
        "XXBTZUSD": {"altname": "XBTUSD", "base": "XXBT", "quote": "ZUSD", "status": "online", "ordermin": "0.0001", "costmin": "0.5"},
        "XETHZEUR": {"altname": "ETHEUR", "base": "XETH", "quote": "ZEUR", "status": "online"},
        "SOMEPAIR": {"altname": "SOMEUSD", "base": "SOME", "quote": "ZUSD", "status": "maintenance"},
    },
}


def _provider(handler) -> KrakenAssetUniverseProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return KrakenAssetUniverseProvider(http_client=client, min_interval_s=0.0)


def test_discover_filters_by_quote_and_maps_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/0/public/AssetPairs"
        return httpx.Response(200, json=_ASSET_PAIRS_PAYLOAD)

    provider = _provider(handler)
    instruments = provider.discover()
    pairs = {inst.exchange_pair: inst for inst in instruments}
    assert "ETHUSD" in pairs  # altname, nu cheia brută "XETHZUSD"
    assert "BTCUSD" in pairs  # "XBTUSD" normalizat -> "BTCUSD" (convenția venue_registry.py)
    assert "XBTUSD" not in pairs
    assert "ETHEUR" not in pairs  # quote filtrat (nu USD)
    assert pairs["SOMEUSD"].status == "cancel_only"  # maintenance mapat conservator


def test_snapshot_parses_ticker_batch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/0/public/Ticker"
        assert "pair" in request.url.params
        return httpx.Response(
            200,
            json={
                "error": [],
                "result": {
                    "XETHZUSD": {"a": ["2510.5", 1, "1"], "b": ["2500.0", 1, "1"], "c": ["2505.0", "1"], "v": ["100", "2000"]},
                },
            },
        )

    provider = _provider(handler)
    snapshots = provider.snapshot(["XETHZUSD"])
    snap = snapshots["XETHZUSD"]
    assert snap.last_price == Decimal("2505.0")
    assert snap.bid == Decimal("2500.0")
    assert snap.ask == Decimal("2510.5")
    assert snap.volume_24h == Decimal("2000")


def test_snapshot_chunks_large_pair_lists() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        pair_param = request.url.params.get("pair")
        calls.append(pair_param)
        pairs = pair_param.split(",")
        result = {
            p: {"a": ["1", 1, "1"], "b": ["1", 1, "1"], "c": ["1", "1"], "v": ["1", "1"]}
            for p in pairs
        }
        return httpx.Response(200, json={"error": [], "result": result})

    provider = _provider(handler)
    many_pairs = [f"PAIR{i}" for i in range(25)]
    snapshots = provider.snapshot(many_pairs)
    assert len(calls) == 2  # batch size 20 -> 20 + 5
    assert len(snapshots) == 25


def test_historical_stats_computes_listing_age_and_window() -> None:
    now = datetime(2026, 9, 20, tzinfo=timezone.utc)
    old_open = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp())
    recent_open = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp())

    def handler(request: httpx.Request) -> httpx.Response:
        since = int(request.url.params["since"])
        # since foarte vechi (>1000 zile) => call pentru listing age
        if since < int(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp()):
            rows = [[old_open, "1", "1", "1", "1", "1", "1", 1]]
        else:
            rows = [[recent_open, "100", "101", "99", "100.5", "100", "50", 1]]
        return httpx.Response(200, json={"error": [], "result": {"XETHZUSD": rows, "last": old_open}})

    provider = _provider(handler)
    stats = provider.historical_stats("XETHZUSD", history_days_requested=90, now=now)
    assert stats.history_days_available == 1
    assert stats.daily_closes == [100.5]
    assert stats.listing_age_days > 900  # de la 2024-01-01


def test_snapshot_translates_altname_to_raw_key_after_discover() -> None:
    """Kraken răspunde la Ticker cu cheia brută AssetPairs, nu cu altname-ul cerut în query."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/0/public/AssetPairs":
            return httpx.Response(200, json=_ASSET_PAIRS_PAYLOAD)
        assert request.url.path == "/0/public/Ticker"
        assert request.url.params["pair"] == "XETHZUSD,XXBTZUSD"  # cheile brute, nu altname
        return httpx.Response(
            200,
            json={
                "error": [],
                "result": {
                    "XETHZUSD": {"a": ["2510.5", 1, "1"], "b": ["2500.0", 1, "1"], "c": ["2505.0", "1"], "v": ["100", "2000"]},
                    "XXBTZUSD": {"a": ["60010", 1, "1"], "b": ["59990", 1, "1"], "c": ["60000", "1"], "v": ["10", "500"]},
                },
            },
        )

    provider = _provider(handler)
    provider.discover()
    snapshots = provider.snapshot(["ETHUSD", "BTCUSD"])
    assert set(snapshots) == {"ETHUSD", "BTCUSD"}
    assert snapshots["ETHUSD"].exchange_pair == "ETHUSD"
    assert snapshots["BTCUSD"].last_price == Decimal("60000")


def test_historical_stats_translates_altname_to_raw_key_after_discover() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/0/public/AssetPairs":
            return httpx.Response(200, json=_ASSET_PAIRS_PAYLOAD)
        assert request.url.path == "/0/public/OHLC"
        assert request.url.params["pair"] == "XXBTZUSD"
        return httpx.Response(
            200,
            json={"error": [], "result": {"XXBTZUSD": [[1700000000, "1", "1", "1", "60000", "1", "1", 1]], "last": 1700000000}},
        )

    provider = _provider(handler)
    provider.discover()
    stats = provider.historical_stats("BTCUSD", now=datetime(2026, 9, 20, tzinfo=timezone.utc))
    assert stats.exchange_pair == "BTCUSD"
    assert stats.daily_closes == [60000.0]


def test_historical_stats_raises_on_missing_series() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": [], "result": {"last": 0}})

    provider = _provider(handler)
    try:
        provider.historical_stats("XETHZUSD", now=datetime(2026, 9, 20, tzinfo=timezone.utc))
        assert False, "expected ValueError"
    except ValueError:
        pass
