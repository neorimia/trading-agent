"""Heartbeat pe fișier. Watchdog-ul îl citește fără să importe engine/."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.runtime_io import write_text_atomic


class Heartbeat:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, process_id: str, timestamp: datetime | None = None) -> None:
        if not process_id.strip():
            raise ValueError("process_id must be a non-empty string")
        moment = timestamp if timestamp is not None else datetime.now(timezone.utc)
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError("heartbeat timestamp must be timezone-aware UTC")
        payload = {
            "process_id": process_id,
            "timestamp": moment.astimezone(timezone.utc).isoformat(),
        }
        write_text_atomic(self._path, json.dumps(payload))

    def is_stale(self, threshold_s: float, *, now: datetime | None = None) -> bool:
        if threshold_s <= 0:
            raise ValueError("threshold_s must be positive")
        if not self._path.is_file():
            return True
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        recorded = datetime.fromisoformat(str(raw["timestamp"]).replace("Z", "+00:00"))
        moment = now if now is not None else datetime.now(timezone.utc)
        age = (moment.astimezone(timezone.utc) - recorded.astimezone(timezone.utc)).total_seconds()
        return age > threshold_s
