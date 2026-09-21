"""Cache local + hash canonic al datasetului (reproductibilitate Task 4)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from src.data.sources import Bar, DataSource, require_utc
from src.data.validation import DataValidator, ValidationReport


def canonical_dataset_hash(bars: list[Bar]) -> str:
    """sha256 peste serializarea canonică (instrument|ts|ohlcv). Ordinea contează."""
    digest = hashlib.sha256()
    for bar in bars:
        ts = require_utc(bar.timestamp, "timestamp").strftime("%Y-%m-%dT%H:%M:%S+00:00")
        line = "|".join(
            [
                bar.instrument,
                ts,
                format(bar.open, "f"),
                format(bar.high, "f"),
                format(bar.low, "f"),
                format(bar.close, "f"),
                format(bar.volume, "f"),
            ]
        )
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _cache_key(instrument: str, start: datetime, end: datetime, timeframe: str) -> str:
    start_s = require_utc(start, "start").strftime("%Y%m%dT%H%M%SZ")
    end_s = require_utc(end, "end").strftime("%Y%m%dT%H%M%SZ")
    return f"{instrument}_{timeframe}_{start_s}_{end_s}.json"


def _bar_to_json(bar: Bar) -> dict[str, str]:
    return {
        "instrument": bar.instrument,
        "timestamp": require_utc(bar.timestamp, "timestamp").strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "open": format(bar.open, "f"),
        "high": format(bar.high, "f"),
        "low": format(bar.low, "f"),
        "close": format(bar.close, "f"),
        "volume": format(bar.volume, "f"),
    }


def _bar_from_json(payload: dict[str, str]) -> Bar:
    from decimal import Decimal

    ts = datetime.fromisoformat(payload["timestamp"])
    return Bar(
        instrument=payload["instrument"],
        timestamp=require_utc(ts, "timestamp"),
        open=Decimal(payload["open"]),
        high=Decimal(payload["high"]),
        low=Decimal(payload["low"]),
        close=Decimal(payload["close"]),
        volume=Decimal(payload["volume"]),
    )


class MarketDataCache:
    def __init__(self, cache_dir: str | Path, source: DataSource) -> None:
        self._cache_dir = Path(cache_dir)
        self._source = source
        self._validator = DataValidator()

    def close(self) -> None:
        """No owned resources; matches `MarketDataRepository.close()` for parity with
        the PostgreSQL-backed cache (src/data/postgres_store.py)."""

    def get_or_fetch(
        self,
        instrument: str,
        start: datetime,
        end: datetime,
        timeframe: str,
        *,
        now: datetime | None = None,
    ) -> tuple[list[Bar], str]:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._cache_dir / _cache_key(instrument, start, end, timeframe)
        if path.is_file():
            bars = self._load(path)
        else:
            bars = self._source.fetch_bars(instrument, start, end, timeframe)
            report = self._validator.validate(bars, timeframe, now=now)
            if not report.ok:
                raise ValueError(_format_report(report))
            self._save(path, instrument, timeframe, start, end, bars)
        dataset_hash = canonical_dataset_hash(bars)
        report = self._validator.validate(bars, timeframe, now=now)
        if not report.ok:
            raise ValueError(_format_report(report))
        return bars, dataset_hash

    def _load(self, path: Path) -> list[Bar]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("bars"), list):
            raise ValueError(f"invalid cache file: {path}")
        return [_bar_from_json(item) for item in raw["bars"]]

    def _save(
        self,
        path: Path,
        instrument: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        bars: list[Bar],
    ) -> None:
        payload = {
            "instrument": instrument,
            "timeframe": timeframe,
            "start": require_utc(start, "start").strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "end": require_utc(end, "end").strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "bars": [_bar_to_json(bar) for bar in bars],
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _format_report(report: ValidationReport) -> str:
    details = "; ".join(f"{issue.code}: {issue.message}" for issue in report.issues)
    return f"market data validation failed: {details}"
