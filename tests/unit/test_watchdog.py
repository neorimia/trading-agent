"""Watchdog flag-only — stale data, poziții nereconciliate, HALT."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from src.execution.broker import BrokerState
from src.execution.reconciliation import LocalPortfolioSnapshot, Reconciliation
from src.monitor.watchdog import Watchdog
from src.risk.kill_switch import KillSwitch


def _watchdog(tmp_path: Path) -> Watchdog:
    return Watchdog(
        kill_switch=KillSwitch(tmp_path / "halt.flag"),
        last_bar_path=tmp_path / "last_bar.json",
        reconciliation_path=tmp_path / "recon.json",
    )


def test_stale_data_when_last_bar_old(tmp_path: Path) -> None:
    watchdog = _watchdog(tmp_path)
    now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
    (tmp_path / "last_bar.json").write_text(
        json.dumps({"timestamp": (now - timedelta(seconds=120)).isoformat()}),
        encoding="utf-8",
    )
    assert watchdog.check_stale_data(30, now=now) is True
    assert watchdog.check_stale_data(180, now=now) is False


def test_missing_last_bar_is_stale(tmp_path: Path) -> None:
    assert _watchdog(tmp_path).check_stale_data(30) is True


def test_unreconciled_positions(tmp_path: Path) -> None:
    watchdog = _watchdog(tmp_path)
    recon = Reconciliation(tmp_path / "recon.json")
    recon.reconcile(
        LocalPortfolioSnapshot(positions={"ETHUSD": Decimal("1")}),
        BrokerState(positions={"ETHUSD": Decimal("0")}),
    )
    assert watchdog.check_unreconciled_positions() is True
    recon.reconcile(
        LocalPortfolioSnapshot(positions={"ETHUSD": Decimal("1")}),
        BrokerState(positions={"ETHUSD": Decimal("1")}),
    )
    assert watchdog.check_unreconciled_positions() is False


def test_set_halt_writes_flag(tmp_path: Path) -> None:
    watchdog = _watchdog(tmp_path)
    watchdog.set_halt("stale_data")
    switch = KillSwitch(tmp_path / "halt.flag")
    assert switch.is_active() is True
