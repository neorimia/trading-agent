"""OHLC public Kraken — DataSource fără autentificare, doar date de piață."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx

from src.data.sources import Bar, require_utc, timeframe_delta
from src.data.venue_registry import UNIVERSE_TO_KRAKEN

KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"

TIMEFRAME_TO_KRAKEN = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


class KrakenPublicOHLCSource:
    """Client REST public. Zero chei. Interzis în procesul llm/."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        base_url: str = KRAKEN_OHLC_URL,
    ) -> None:
        self._http_client = http_client
        self._owns_client = http_client is None
        self._base_url = base_url

    def close(self) -> None:
        if self._owns_client and self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def _client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=30.0)
        return self._http_client

    def fetch_bars(
        self,
        instrument: str,
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> list[Bar]:
        pair = UNIVERSE_TO_KRAKEN.get(instrument)
        if pair is None:
            raise ValueError(f"no Kraken mapping for instrument {instrument!r}")
        interval = TIMEFRAME_TO_KRAKEN.get(timeframe)
        if interval is None:
            raise ValueError(f"unsupported timeframe: {timeframe}")
        start_utc = require_utc(start, "start")
        end_utc = require_utc(end, "end")
        if end_utc <= start_utc:
            raise ValueError("end must be after start")

        response = self._client().get(
            self._base_url,
            params={
                "pair": pair,
                "interval": interval,
                "since": int(start_utc.timestamp()) - 1,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("unexpected Kraken OHLC payload")
        errors = payload.get("error") or []
        if errors:
            raise ValueError(f"Kraken OHLC error: {errors}")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError("Kraken OHLC result missing")
        series = None
        for key, value in result.items():
            if key == "last":
                continue
            series = value
            break
        if not isinstance(series, list):
            raise ValueError("Kraken OHLC series missing")

        delta = timeframe_delta(timeframe)
        bars: list[Bar] = []
        for row in series:
            if not isinstance(row, list) or len(row) < 7:
                raise ValueError("unexpected Kraken OHLC row")
            open_ts = datetime.fromtimestamp(int(row[0]), tz=timezone.utc)
            close_ts = open_ts + delta - timedelta(seconds=1)
            if close_ts < start_utc or close_ts > end_utc:
                continue
            bars.append(
                Bar(
                    instrument=instrument,
                    timestamp=close_ts,
                    open=Decimal(str(row[1])),
                    high=Decimal(str(row[2])),
                    low=Decimal(str(row[3])),
                    close=Decimal(str(row[4])),
                    volume=Decimal(str(row[6])),
                )
            )
        return bars
