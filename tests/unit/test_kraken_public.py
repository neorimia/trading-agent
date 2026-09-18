"""Kraken public OHLC — fără auth, mapare ETHUSD."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import httpx

from src.data.kraken import KrakenPublicOHLCSource


def test_kraken_source_parses_public_ohlc() -> None:
    open_ts = int(datetime(2024, 11, 1, tzinfo=timezone.utc).timestamp())

    def handler(request: httpx.Request) -> httpx.Response:
        assert "pair=ETHUSD" in str(request.url)
        assert "interval=1440" in str(request.url)
        return httpx.Response(
            200,
            json={
                "error": [],
                "result": {
                    "XETHZUSD": [
                        [
                            open_ts,
                            "2500.0",
                            "2550.0",
                            "2480.0",
                            "2520.0",
                            "2510.0",
                            "100.5",
                            12,
                        ]
                    ],
                    "last": open_ts,
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    source = KrakenPublicOHLCSource(http_client=client)
    bars = source.fetch_bars(
        "ETHUSD",
        datetime(2024, 11, 1, tzinfo=timezone.utc),
        datetime(2024, 11, 2, tzinfo=timezone.utc),
        "1d",
    )
    assert len(bars) == 1
    assert bars[0].instrument == "ETHUSD"
    assert bars[0].close == Decimal("2520.0")
    assert bars[0].volume == Decimal("100.5")
    assert bars[0].timestamp.tzinfo is not None
