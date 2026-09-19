"""Plan zilnic determinist (P7). Template UTC 00:00, fără evenimente inventate."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence


def _require_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware UTC")
    return moment.astimezone(timezone.utc)


def build_daily_plan(
    *,
    instrument: str,
    as_of: datetime,
    indicators: dict[str, Any],
    remaining_daily_loss: str,
    remaining_drawdown: str,
    remaining_orders_today: int,
    calendar_events: Sequence[str],
    document_titles: Sequence[str],
    venue_stale: bool,
) -> dict[str, Any]:
    """Checklist repetabil. calendar_events e injectat — gol înseamnă 'none listed'."""
    moment = _require_utc(as_of)
    events = list(calendar_events) if calendar_events else ["none listed"]
    docs = list(document_titles) if document_titles else ["none listed"]
    return {
        "instrument": instrument,
        "session_start_utc": datetime(
            moment.year, moment.month, moment.day, tzinfo=timezone.utc
        ).isoformat(),
        "as_of": moment.isoformat(),
        "checklist": [
            {"phase": "session_open_utc", "item": "pre-session news and catalysts", "value": docs},
            {"phase": "session_open_utc", "item": "economic / protocol calendar", "value": events},
            {"phase": "session_open_utc", "item": "major price levels", "value": indicators},
            {"phase": "session_open_utc", "item": "unusual volume", "value": indicators.get("volume_z_20", "unknown")},
            {"phase": "intraday", "item": "watchlist", "value": [instrument]},
            {"phase": "intraday", "item": "session scenarios", "value": "fill from research analysis only"},
            {"phase": "intraday", "item": "risk limits remaining", "value": {
                "remaining_daily_loss": remaining_daily_loss,
                "remaining_drawdown": remaining_drawdown,
                "remaining_orders_today": remaining_orders_today,
            }},
            {"phase": "session_close_utc", "item": "end-of-day review", "value": "journal fills vs thesis"},
        ],
        "blocks_trading": venue_stale,
        "block_reason": "venue_stale" if venue_stale else None,
    }
