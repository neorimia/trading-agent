"""DataValidator: gap-uri, duplicate, timestamp-viitor — fără reparare silențioasă."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from src.data.sources import Bar
from src.data.validation import DataValidator


def _bar(day: int, close: str = "100", ts_hour: int = 23) -> Bar:
    return Bar(
        instrument="ETHUSD",
        timestamp=datetime(2024, 11, day, ts_hour, 59, 59, tzinfo=timezone.utc),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal(close),
        volume=Decimal("10"),
    )


def test_valid_consecutive_daily_bars_pass() -> None:
    report = DataValidator().validate(
        [_bar(1), _bar(2), _bar(3)],
        "1d",
        now=datetime(2024, 12, 1, tzinfo=timezone.utc),
    )
    assert report.ok is True
    assert report.issues == []


def test_empty_series_fails() -> None:
    report = DataValidator().validate([], "1d")
    assert report.ok is False
    assert report.issues[0].code == "empty"


def test_duplicate_timestamp_fails() -> None:
    report = DataValidator().validate(
        [_bar(1), _bar(1, close="101"), _bar(2)],
        "1d",
        now=datetime(2024, 12, 1, tzinfo=timezone.utc),
    )
    assert report.ok is False
    assert any(issue.code == "duplicate" for issue in report.issues)


def test_gap_fails() -> None:
    report = DataValidator().validate(
        [_bar(1), _bar(3)],
        "1d",
        now=datetime(2024, 12, 1, tzinfo=timezone.utc),
    )
    assert report.ok is False
    assert any(issue.code == "gap" for issue in report.issues)


def test_future_timestamp_fails() -> None:
    report = DataValidator().validate(
        [_bar(1), _bar(2)],
        "1d",
        now=datetime(2024, 11, 1, 12, 0, tzinfo=timezone.utc),
    )
    assert report.ok is False
    assert any(issue.code == "future_timestamp" for issue in report.issues)


def test_out_of_order_fails() -> None:
    report = DataValidator().validate(
        [_bar(2), _bar(1)],
        "1d",
        now=datetime(2024, 12, 1, tzinfo=timezone.utc),
    )
    assert report.ok is False
    assert any(issue.code == "out_of_order" for issue in report.issues)
