"""Surse de bare: Binance public klines (fără auth) și CSV local pentru teste.

`venue: KRAKEN` din universe.yaml rămâne ruta de execuție (Faza 5). Istoricul
de backtest e luat de pe Binance public API pentru că paginarea pe intervale
lungi e posibilă; Kraken OHLC public întoarce ~720 lumânări.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Protocol

import httpx

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_MAX_LIMIT = 1000

# Simbolul din universe.yaml → perechea spot Binance folosită doar ca istoric.
UNIVERSE_TO_BINANCE = {
    "ETHUSD": "ETHUSDT",
    "BTCUSD": "BTCUSDT",
}

TIMEFRAME_TO_BINANCE = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}

TIMEFRAME_DELTA = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


@dataclass(frozen=True)
class Bar:
    """Bară OHLCV. `timestamp` e close-time UTC (lookahead-safe: bara e cunoscută la închidere)."""

    instrument: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class DataSource(Protocol):
    def fetch_bars(
        self,
        instrument: str,
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> list[Bar]:
        ...


def timeframe_delta(timeframe: str) -> timedelta:
    if timeframe not in TIMEFRAME_DELTA:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    return TIMEFRAME_DELTA[timeframe]


def require_utc(moment: datetime, field_name: str) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return moment.astimezone(timezone.utc)


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _ms(moment: datetime) -> int:
    return int(require_utc(moment, "timestamp").timestamp() * 1000)


def _close_time_utc(close_time_ms: int) -> datetime:
    # Binance closeTime e sfârșitul ferestrei (ms). Truncăm la secundă UTC.
    seconds = close_time_ms // 1000
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


class BinanceKlinesSource:
    """Client REST public, fără credențiale. Interzis în procesul llm/ (trăiește în data/)."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        base_url: str = BINANCE_KLINES_URL,
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
        symbol = UNIVERSE_TO_BINANCE.get(instrument)
        if symbol is None:
            raise ValueError(f"no Binance mapping for instrument {instrument!r}")
        interval = TIMEFRAME_TO_BINANCE.get(timeframe)
        if interval is None:
            raise ValueError(f"unsupported timeframe: {timeframe}")
        start_utc = require_utc(start, "start")
        end_utc = require_utc(end, "end")
        if end_utc <= start_utc:
            raise ValueError("end must be after start")

        bars: list[Bar] = []
        cursor_ms = _ms(start_utc)
        end_ms = _ms(end_utc)
        while cursor_ms < end_ms:
            response = self._client().get(
                self._base_url,
                params={
                    "symbol": symbol,
                    "interval": interval,
                    "startTime": cursor_ms,
                    "endTime": end_ms,
                    "limit": BINANCE_MAX_LIMIT,
                },
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list) or not payload:
                break
            last_open_ms: int | None = None
            for row in payload:
                if not isinstance(row, list) or len(row) < 8:
                    raise ValueError("unexpected kline payload shape")
                open_ms = int(row[0])
                close_ms = int(row[6])
                last_open_ms = open_ms
                ts = _close_time_utc(close_ms)
                if ts < start_utc or ts > end_utc:
                    continue
                bars.append(
                    Bar(
                        instrument=instrument,
                        timestamp=ts,
                        open=_decimal(row[1]),
                        high=_decimal(row[2]),
                        low=_decimal(row[3]),
                        close=_decimal(row[4]),
                        volume=_decimal(row[5]),
                    )
                )
            if last_open_ms is None or len(payload) < BINANCE_MAX_LIMIT:
                break
            cursor_ms = last_open_ms + 1
        return bars


class CsvBarDataSource:
    """Sursă locală, zero rețea — pentru teste și fixtures pinned."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def fetch_bars(
        self,
        instrument: str,
        start: datetime,
        end: datetime,
        timeframe: str,  # noqa: ARG002 — protocol compatibility
    ) -> list[Bar]:
        if not self._path.is_file():
            raise ValueError(f"CSV bars file missing: {self._path}")
        start_utc = require_utc(start, "start")
        end_utc = require_utc(end, "end")
        bars: list[Bar] = []
        lines = self._path.read_text(encoding="utf-8").splitlines()
        if not lines:
            raise ValueError("CSV bars file is empty")
        header = [col.strip() for col in lines[0].split(",")]
        expected = ["timestamp", "open", "high", "low", "close", "volume"]
        if header != expected:
            raise ValueError(f"CSV header must be {expected}, got {header}")
        for raw in lines[1:]:
            if not raw.strip() or raw.strip().startswith("#"):
                continue
            parts = [p.strip() for p in raw.split(",")]
            if len(parts) != 6:
                raise ValueError(f"CSV row must have 6 columns: {raw}")
            ts = datetime.fromisoformat(parts[0].replace("Z", "+00:00"))
            ts = require_utc(ts, "timestamp")
            if ts < start_utc or ts > end_utc:
                continue
            bars.append(
                Bar(
                    instrument=instrument,
                    timestamp=ts,
                    open=_decimal(parts[1]),
                    high=_decimal(parts[2]),
                    low=_decimal(parts[3]),
                    close=_decimal(parts[4]),
                    volume=_decimal(parts[5]),
                )
            )
        return bars


def bars_to_iterable(bars: list[Bar]) -> Iterable[Bar]:
    return iter(bars)
