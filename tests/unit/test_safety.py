"""HaltAndFlatten + PeriodicReconciler: mismatch → kill switch + cancel_all."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from src.execution.broker import BrokerState, SimulatedBroker
from src.execution.reconciliation import LocalPortfolioSnapshot, Reconciliation
from src.execution.safety import HaltAndFlatten, PeriodicReconciler
from src.monitor.watchdog import Watchdog
from src.risk.kill_switch import KillSwitch


def test_mismatch_halts_and_cancels(tmp_path: Path) -> None:
    kill = KillSwitch(tmp_path / "halt.flag")
    watchdog = Watchdog(
        kill_switch=kill,
        last_bar_path=tmp_path / "last_bar.json",
        reconciliation_path=tmp_path / "recon.json",
    )
    broker = SimulatedBroker()
    broker.set_last_price("ETHUSD", Decimal("2500"))
    cancelled: list[str] = []
    flatten = HaltAndFlatten(watchdog, lambda reason: cancelled.append(reason) or broker.cancel_all(reason))
    periodic = PeriodicReconciler(Reconciliation(tmp_path / "recon.json"), flatten)

    report = periodic.run(
        LocalPortfolioSnapshot(positions={"ETHUSD": Decimal("1")}),
        BrokerState(positions={"ETHUSD": Decimal("0")}),
    )
    assert report.matched is False
    assert kill.is_active() is True
    assert cancelled == ["reconciliation_mismatch"]


def test_match_does_not_halt(tmp_path: Path) -> None:
    kill = KillSwitch(tmp_path / "halt.flag")
    watchdog = Watchdog(
        kill_switch=kill,
        last_bar_path=tmp_path / "last_bar.json",
        reconciliation_path=tmp_path / "recon.json",
    )
    cancelled: list[str] = []
    periodic = PeriodicReconciler(
        Reconciliation(tmp_path / "recon.json"),
        HaltAndFlatten(watchdog, lambda reason: cancelled.append(reason)),
    )
    report = periodic.run(
        LocalPortfolioSnapshot(positions={"ETHUSD": Decimal("1")}),
        BrokerState(positions={"ETHUSD": Decimal("1")}),
    )
    assert report.matched is True
    assert kill.is_active() is False
    assert cancelled == []
