"""Plan zilnic determinist: calendar gol = none listed, nu evenimente inventate."""

from __future__ import annotations

from datetime import datetime, timezone

from src.engine.daily_plan import build_daily_plan


def test_empty_calendar_stays_none_listed() -> None:
    plan = build_daily_plan(
        instrument="ETHUSD",
        as_of=datetime(2026, 9, 18, 12, tzinfo=timezone.utc),
        indicators={"close": "2410", "volume_z_20": "unknown"},
        remaining_daily_loss="1000",
        remaining_drawdown="2000",
        remaining_orders_today=8,
        calendar_events=[],
        document_titles=[],
        venue_stale=False,
    )
    calendar = next(item for item in plan["checklist"] if item["item"] == "economic / protocol calendar")
    news = next(item for item in plan["checklist"] if item["item"] == "pre-session news and catalysts")
    risk = next(item for item in plan["checklist"] if item["item"] == "risk limits remaining")
    assert calendar["value"] == ["none listed"]
    assert news["value"] == ["none listed"]
    assert risk["value"]["remaining_orders_today"] == 8
    assert plan["session_start_utc"].startswith("2026-09-18T00:00:00")
    assert plan["blocks_trading"] is False


def test_stale_venue_blocks_trading_flag() -> None:
    plan = build_daily_plan(
        instrument="BTCUSD",
        as_of=datetime(2026, 9, 18, tzinfo=timezone.utc),
        indicators={},
        remaining_daily_loss="0",
        remaining_drawdown="0",
        remaining_orders_today=0,
        calendar_events=["FOMC"],
        document_titles=["upgrade notes"],
        venue_stale=True,
    )
    assert plan["blocks_trading"] is True
    assert plan["block_reason"] == "venue_stale"
    calendar = next(item for item in plan["checklist"] if item["item"] == "economic / protocol calendar")
    assert calendar["value"] == ["FOMC"]
