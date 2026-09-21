"""Paper stream: closed-bar poll, seed without sessions, persist across restart."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from src.data.sources import Bar
from src.engine.strategy_paper import PaperTradingLoop
from src.execution.reconciliation import LocalPortfolioSnapshot, Reconciliation
from src.execution.broker import BrokerState
from src.monitor.broker_monitor import BrokerMonitorSnapshot, write_broker_monitor

from tests.integration.test_paper_trading_flow import _bars, build_loop


def _bar_at(index: int, close: str = "2500") -> Bar:
    stamp = datetime(2024, 11, 1, tzinfo=timezone.utc) + timedelta(days=index)
    price = Decimal(close) + Decimal(index)
    return Bar(
        instrument="ETHUSD",
        timestamp=stamp.replace(hour=23, minute=59, second=59),
        open=price,
        high=price + Decimal("10"),
        low=price - Decimal("10"),
        close=price,
        volume=Decimal("10000"),
    )


def test_seed_history_does_not_create_sessions(tmp_path: Path) -> None:
    loop, audit, _broker, _halt = build_loop(tmp_path)
    bars = [_bar_at(i) for i in range(20)]
    loop.seed_history(bars)
    assert loop._history[-1].timestamp == bars[-1].timestamp  # noqa: SLF001
    types = [event.event_type for event in audit.list_events()]
    assert "proposal" not in types
    assert "order_submitted" not in types


def test_stream_first_poll_is_warmup_second_poll_sessions(tmp_path: Path) -> None:
    loop, _audit, broker, halt = build_loop(tmp_path)
    bars = [_bar_at(i) for i in range(22)]
    polls = {"n": 0}

    def poll(_after: datetime | None) -> list[Bar]:
        polls["n"] += 1
        if polls["n"] == 1:
            return bars[:21]
        return bars[:22]

    result = loop.run_stream(
        poll,
        poll_interval_s=0,
        sleep_fn=lambda _s: None,
        max_polls=2,
    )
    assert polls["n"] == 2
    assert len(result.sessions) == 1
    assert result.sessions[0].halted is False
    assert halt.is_active() is False
    assert broker.snapshot().positions.get("ETHUSD", Decimal("0")) > 0


def test_stream_ignores_duplicate_bars(tmp_path: Path) -> None:
    loop, _audit, _broker, _halt = build_loop(tmp_path)
    bars = [_bar_at(i) for i in range(21)]

    def poll(_after: datetime | None) -> list[Bar]:
        return bars

    result = loop.run_stream(
        poll,
        poll_interval_s=0,
        sleep_fn=lambda _s: None,
        max_polls=3,
    )
    assert result.sessions == []


def test_restart_restores_broker_and_tracker(tmp_path: Path) -> None:
    loop1, _audit1, broker1, _halt1 = build_loop(tmp_path)
    result = loop1.run_bars(_bars(), max_sessions=1)
    assert result.sessions
    assert broker1.snapshot().positions["ETHUSD"] > 0
    qty = broker1.snapshot().positions["ETHUSD"]
    cash = loop1._tracker.dump_state()["cash"]  # noqa: SLF001

    loop2, _audit2, broker2, halt2 = build_loop(tmp_path)
    loop2.restore_persisted_state()
    loop2.reconcile_startup()
    assert halt2.is_active() is False
    assert broker2.snapshot().positions["ETHUSD"] == qty
    assert loop2._tracker.dump_state()["cash"] == cash  # noqa: SLF001


def test_run_bar_exception_halts_instead_of_crashing(tmp_path: Path) -> None:
    """An exception inside run_bar must halt (fail-closed), not propagate and kill the loop."""
    loop, audit, _broker, halt = build_loop(tmp_path)
    bars = [_bar_at(i) for i in range(22)]
    polls = {"n": 0}

    def poll(_after: datetime | None) -> list[Bar]:
        polls["n"] += 1
        if polls["n"] == 1:
            return bars[:21]  # seeded on first poll (last_ts is None)
        return bars[:22]  # one new bar on second poll -> run_bar is called

    def boom(_bar: Bar) -> None:
        raise RuntimeError("simulated run_bar failure")

    loop.run_bar = boom  # type: ignore[method-assign]

    result = loop.run_stream(
        poll,
        poll_interval_s=0,
        sleep_fn=lambda _s: None,
        max_polls=2,
    )
    assert result.sessions == []
    assert halt.is_active() is True
    types = [event.event_type for event in audit.list_events()]
    assert "run_bar_error" in types
    assert "halt" in types


def test_paper_recon_does_not_read_broker_monitor_file(tmp_path: Path) -> None:
    write_broker_monitor(
        tmp_path / "broker_monitor.json",
        BrokerMonitorSnapshot(
            status="polling",
            positions={"ETHUSD": "99"},
            open_client_order_ids=["live-order"],
        ),
    )
    recon = Reconciliation(tmp_path / "recon.json")
    local = LocalPortfolioSnapshot(positions={"ETHUSD": Decimal("0.1")})
    broker = BrokerState(positions={"ETHUSD": Decimal("0.1")})
    report = recon.reconcile(local, broker)
    assert report.matched is True
    assert "99" not in (tmp_path / "recon.json").read_text(encoding="utf-8")
