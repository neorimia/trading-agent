"""Heartbeat pe fișier."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.monitor.heartbeat import Heartbeat


def test_write_and_fresh(tmp_path: Path) -> None:
    beat = Heartbeat(tmp_path / "hb.json")
    now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
    beat.write("paper-engine", now)
    assert beat.is_stale(30, now=now) is False
    assert beat.is_stale(30, now=now + timedelta(seconds=31)) is True


def test_missing_file_is_stale(tmp_path: Path) -> None:
    beat = Heartbeat(tmp_path / "missing.json")
    assert beat.is_stale(30) is True
