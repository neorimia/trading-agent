"""PortfolioTracker structured trade round-trips (design Phase 6, §8.6 `backtest_trades`).

Covers the `ClosedTrade`/`on_fill(timestamp=...)` extension added for Phase 6: entry
time/price tracking across partial sells, `dump_state`/`restore` symmetry, and the
existing PnL-only `closed_trades` list staying untouched for `src/engine/metrics.py`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.engine.portfolio_tracker import ClosedTrade, PortfolioTracker

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _tracker() -> PortfolioTracker:
    return PortfolioTracker(Decimal("10000"), "ETHUSD", "crypto")


def test_on_fill_buy_then_sell_records_structured_closed_trade() -> None:
    tracker = _tracker()
    t_entry = T0
    t_exit = T0 + timedelta(hours=1)

    tracker.on_fill(
        side="buy", quantity=Decimal("1"), price=Decimal("100"),
        commission=Decimal("0.1"), timestamp=t_entry,
    )
    tracker.on_fill(
        side="sell", quantity=Decimal("1"), price=Decimal("110"),
        commission=Decimal("0.2"), timestamp=t_exit, exit_reason="take_profit",
    )

    # Legacy PnL-only list stays as-is (src/engine/metrics.py compatibility).
    assert tracker.closed_trades == [Decimal("10")]

    records = tracker.closed_trade_records
    assert len(records) == 1
    record = records[0]
    assert record == ClosedTrade(
        side="buy",
        entry_time=t_entry,
        entry_price=Decimal("100"),
        exit_time=t_exit,
        exit_price=Decimal("110"),
        quantity=Decimal("1"),
        pnl=Decimal("10"),
        fees=Decimal("0.2"),  # only the closing fill's commission (module docstring)
        exit_reason="take_profit",
    )


def test_on_fill_without_timestamp_kwarg_is_a_type_error() -> None:
    """`timestamp` is a required keyword now (Phase 6 round-trip-tracker change) —
    callers (strategy_adapter/strategy_baseline/strategy_llm_assisted/strategy_paper)
    must always pass the bar time, never rely on a default."""
    tracker = _tracker()
    try:
        tracker.on_fill(  # type: ignore[call-arg]
            side="buy", quantity=Decimal("1"), price=Decimal("100"), commission=Decimal("0")
        )
    except TypeError:
        pass
    else:
        raise AssertionError("on_fill should require timestamp")


def test_partial_sell_keeps_entry_time_for_remaining_position() -> None:
    """Buying 2, selling 1, then selling the remaining 1 must report the same
    original entry_time for both closed trades — the weighted-average entry is
    only reset once the position returns to flat (module docstring 'unchanged by
    later same-direction adds')."""
    tracker = _tracker()
    t_entry = T0
    t_exit_1 = T0 + timedelta(hours=1)
    t_exit_2 = T0 + timedelta(hours=2)

    tracker.on_fill(
        side="buy", quantity=Decimal("2"), price=Decimal("100"),
        commission=Decimal("0"), timestamp=t_entry,
    )
    tracker.on_fill(
        side="sell", quantity=Decimal("1"), price=Decimal("110"),
        commission=Decimal("0"), timestamp=t_exit_1,
    )
    tracker.on_fill(
        side="sell", quantity=Decimal("1"), price=Decimal("120"),
        commission=Decimal("0"), timestamp=t_exit_2,
    )

    records = tracker.closed_trade_records
    assert len(records) == 2
    assert records[0].entry_time == t_entry
    assert records[0].exit_time == t_exit_1
    assert records[1].entry_time == t_entry
    assert records[1].exit_time == t_exit_2


def test_buy_after_full_exit_starts_a_new_entry_time() -> None:
    tracker = _tracker()
    t1, t2, t3, t4 = (T0 + timedelta(hours=i) for i in range(4))

    tracker.on_fill(side="buy", quantity=Decimal("1"), price=Decimal("100"), commission=Decimal("0"), timestamp=t1)
    tracker.on_fill(side="sell", quantity=Decimal("1"), price=Decimal("105"), commission=Decimal("0"), timestamp=t2)
    tracker.on_fill(side="buy", quantity=Decimal("1"), price=Decimal("106"), commission=Decimal("0"), timestamp=t3)
    tracker.on_fill(side="sell", quantity=Decimal("1"), price=Decimal("108"), commission=Decimal("0"), timestamp=t4)

    records = tracker.closed_trade_records
    assert len(records) == 2
    assert records[0].entry_time == t1
    assert records[1].entry_time == t3  # new entry, not t1


def test_dump_state_and_restore_round_trips_closed_trade_records() -> None:
    tracker = _tracker()
    t_entry = T0
    t_exit = T0 + timedelta(hours=1)
    tracker.on_fill(
        side="buy", quantity=Decimal("1"), price=Decimal("100"),
        commission=Decimal("0.1"), timestamp=t_entry,
    )
    tracker.on_fill(
        side="sell", quantity=Decimal("1"), price=Decimal("110"),
        commission=Decimal("0.2"), timestamp=t_exit, exit_reason="stop_loss",
    )

    state = tracker.dump_state()
    assert state["closed_trade_records"][0]["exit_reason"] == "stop_loss"
    assert state["entry_time"] is None  # flat again after the sell closed the position

    restored = _tracker()
    restored.restore(state)

    assert restored.closed_trade_records == tracker.closed_trade_records
    assert restored.closed_trades == tracker.closed_trades


def test_dump_state_round_trips_open_entry_time_when_position_still_open() -> None:
    tracker = _tracker()
    t_entry = T0
    tracker.on_fill(
        side="buy", quantity=Decimal("1"), price=Decimal("100"),
        commission=Decimal("0"), timestamp=t_entry,
    )

    state = tracker.dump_state()
    assert state["entry_time"] == t_entry.isoformat()

    restored = _tracker()
    restored.restore(state)

    # Closing the restored position must reuse the original entry_time, proving
    # `_entry_time` itself (not just the records list) round-tripped correctly.
    t_exit = T0 + timedelta(hours=3)
    restored.on_fill(
        side="sell", quantity=Decimal("1"), price=Decimal("120"),
        commission=Decimal("0"), timestamp=t_exit,
    )
    assert restored.closed_trade_records[-1].entry_time == t_entry


def test_zero_quantity_fill_is_ignored() -> None:
    tracker = _tracker()
    tracker.on_fill(
        side="buy", quantity=Decimal("0"), price=Decimal("100"),
        commission=Decimal("0"), timestamp=T0,
    )
    assert tracker.closed_trade_records == []
    assert tracker.equity(Decimal("100")) == Decimal("10000")
