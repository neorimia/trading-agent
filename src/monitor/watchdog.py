"""Watchdog flag-only — design §2: fără client de broker propriu."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.execution.reconciliation import ReconciliationReport
from src.risk.kill_switch import KillSwitch


class Watchdog:
    """Citește runtime/ (heartbeat, last_bar, reconciliation). HALT prin KillSwitch."""

    def __init__(
        self,
        *,
        kill_switch: KillSwitch,
        last_bar_path: str | Path,
        reconciliation_path: str | Path,
    ) -> None:
        self._kill_switch = kill_switch
        self._last_bar_path = Path(last_bar_path)
        self._reconciliation_path = Path(reconciliation_path)

    def check_stale_data(self, threshold_s: float, *, now: datetime | None = None) -> bool:
        if threshold_s <= 0:
            raise ValueError("threshold_s must be positive")
        if not self._last_bar_path.is_file():
            return True
        raw = json.loads(self._last_bar_path.read_text(encoding="utf-8"))
        recorded = datetime.fromisoformat(str(raw["timestamp"]).replace("Z", "+00:00"))
        moment = now if now is not None else datetime.now(timezone.utc)
        age = (moment.astimezone(timezone.utc) - recorded.astimezone(timezone.utc)).total_seconds()
        return age > threshold_s

    def check_unreconciled_positions(self) -> bool:
        if not self._reconciliation_path.is_file():
            return True
        report = ReconciliationReport.model_validate_json(
            self._reconciliation_path.read_text(encoding="utf-8")
        )
        return not report.matched

    def set_halt(self, reason: str) -> None:
        self._kill_switch.trigger(reason)
