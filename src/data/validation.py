"""Validare hard a seriilor OHLCV: gap-uri, duplicate, timestamp-uri în viitor.

Nu repară silențios — un raport cu `ok=False` trebuie tratat ca eșec de către caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.data.sources import Bar, timeframe_delta


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str


@dataclass
class ValidationReport:
    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)


class DataValidator:
    def validate(
        self,
        bars: list[Bar],
        timeframe: str,
        *,
        now: datetime | None = None,
    ) -> ValidationReport:
        issues: list[ValidationIssue] = []
        if not bars:
            issues.append(ValidationIssue("empty", "bar series is empty"))
            return ValidationReport(ok=False, issues=issues)

        clock = now if now is not None else datetime.now(timezone.utc)
        if clock.tzinfo is None or clock.utcoffset() is None:
            raise ValueError("now must be timezone-aware UTC")
        clock = clock.astimezone(timezone.utc)
        interval = timeframe_delta(timeframe)

        seen: dict[datetime, int] = {}
        previous: Bar | None = None
        expected_instrument = bars[0].instrument
        for index, bar in enumerate(bars):
            if bar.instrument != expected_instrument:
                issues.append(
                    ValidationIssue(
                        "mixed_instrument",
                        f"bar[{index}] instrument {bar.instrument!r} != {expected_instrument!r}",
                    )
                )
            if bar.timestamp.tzinfo is None or bar.timestamp.utcoffset() is None:
                issues.append(
                    ValidationIssue("naive_timestamp", f"bar[{index}] timestamp is not UTC-aware")
                )
            elif bar.timestamp > clock:
                issues.append(
                    ValidationIssue(
                        "future_timestamp",
                        f"bar[{index}] timestamp {bar.timestamp.isoformat()} is in the future",
                    )
                )
            if bar.high < bar.low:
                issues.append(
                    ValidationIssue("ohlc", f"bar[{index}] high < low")
                )
            if bar.high < bar.open or bar.high < bar.close or bar.low > bar.open or bar.low > bar.close:
                issues.append(
                    ValidationIssue("ohlc", f"bar[{index}] OHLC bounds violated")
                )
            if bar.volume < 0:
                issues.append(ValidationIssue("volume", f"bar[{index}] negative volume"))

            count = seen.get(bar.timestamp, 0) + 1
            seen[bar.timestamp] = count
            if count == 2:
                issues.append(
                    ValidationIssue(
                        "duplicate",
                        f"duplicate timestamp {bar.timestamp.isoformat()}",
                    )
                )

            if previous is not None:
                if bar.timestamp < previous.timestamp:
                    issues.append(
                        ValidationIssue(
                            "out_of_order",
                            f"bar[{index}] timestamp precedes previous bar",
                        )
                    )
                else:
                    delta = bar.timestamp - previous.timestamp
                    if delta > interval:
                        issues.append(
                            ValidationIssue(
                                "gap",
                                f"gap between {previous.timestamp.isoformat()} and "
                                f"{bar.timestamp.isoformat()} (delta={delta}, expected={interval})",
                            )
                        )
            previous = bar

        return ValidationReport(ok=not issues, issues=issues)
