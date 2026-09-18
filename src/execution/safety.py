"""Halt + flatten: Watchdog → KillSwitch → cancel_all pe gateway."""

from __future__ import annotations

from collections.abc import Callable

from src.execution.broker import BrokerState
from src.execution.reconciliation import (
    LocalPortfolioSnapshot,
    Reconciliation,
    ReconciliationReport,
)
from src.monitor.watchdog import Watchdog


class HaltAndFlatten:
    """Un singur punct: HALT pe fișier și anulare ordine deschise."""

    def __init__(
        self,
        watchdog: Watchdog,
        cancel_all: Callable[[str], None],
    ) -> None:
        self._watchdog = watchdog
        self._cancel_all = cancel_all

    def trigger(self, reason: str) -> None:
        self._watchdog.set_halt(reason)
        self._cancel_all(reason)


class PeriodicReconciler:
    """Reconciliere la pornire / periodică. Mismatch → HaltAndFlatten."""

    def __init__(self, reconciliation: Reconciliation, halt: HaltAndFlatten) -> None:
        self._reconciliation = reconciliation
        self._halt = halt

    def run(
        self,
        local_state: LocalPortfolioSnapshot,
        broker_state: BrokerState,
    ) -> ReconciliationReport:
        report = self._reconciliation.reconcile(local_state, broker_state)
        if not report.matched:
            self._halt.trigger("reconciliation_mismatch")
        return report
