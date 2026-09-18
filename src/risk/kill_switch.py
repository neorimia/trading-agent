"""Kill switch independent — stare externă pe fișier, nu variabilă de proces.

Apelabil manual și din monitor/; RiskEngine îl citește la fiecare evaluate().
reset() e o acțiune umană explicită — nu e apelat din fluxul automat de decizie.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")


class KillSwitchResult(BaseModel):
    model_config = _STRICT

    triggered: bool
    reason: str = Field(min_length=1)
    triggered_at: datetime


class KillSwitch:
    """Semnal HALT partajat prin `runtime/control/halt.flag` (sau alt path injectat)."""

    def __init__(self, flag_path: str | Path) -> None:
        self._flag_path = Path(flag_path)

    @property
    def flag_path(self) -> Path:
        return self._flag_path

    def trigger(self, reason: str) -> KillSwitchResult:
        """Scrie flag-ul. Idempotent: un al doilea apel lasă sistemul tot în HALT."""
        cleaned = reason.strip()
        if not cleaned:
            raise ValueError("kill switch reason must be a non-empty string")
        triggered_at = datetime.now(timezone.utc)
        payload = {
            "reason": cleaned,
            "triggered_at": triggered_at.isoformat(),
        }
        self._flag_path.parent.mkdir(parents=True, exist_ok=True)
        self._flag_path.write_text(json.dumps(payload), encoding="utf-8")
        return KillSwitchResult(triggered=True, reason=cleaned, triggered_at=triggered_at)

    def is_active(self) -> bool:
        return self._flag_path.is_file()

    def reset(self) -> None:
        """Șterge flag-ul. Doar acțiune manuală — reluare după HALT nu e automată."""
        if self._flag_path.is_file():
            self._flag_path.unlink()
