"""Circuit breaker — stare RUNNING/HALTED, reluare doar prin kill switch manual."""

from __future__ import annotations

from typing import Literal

from src.risk.config_schema import CircuitBreakerLimits
from src.risk.kill_switch import KillSwitch

CircuitBreakerOutcome = Literal["success", "error", "loss", "unknown_result"]
CircuitBreakerState = Literal["RUNNING", "HALTED"]


class CircuitBreaker:
    """Contoare consecutive în memorie; tranziția spre HALTED scrie flag-ul de control."""

    def __init__(self, limits: CircuitBreakerLimits, kill_switch: KillSwitch) -> None:
        self._limits = limits
        self._kill_switch = kill_switch
        self._consecutive_errors = 0
        self._consecutive_losses = 0

    @property
    def state(self) -> CircuitBreakerState:
        # Sursa de adevăr e flag-ul extern, ca RiskEngine să vadă HALT-ul
        # indiferent de instanța care l-a declanșat.
        return "HALTED" if self._kill_switch.is_active() else "RUNNING"

    def record_event(self, outcome: CircuitBreakerOutcome) -> None:
        if self.state == "HALTED":
            return
        if outcome == "success":
            self._consecutive_errors = 0
            self._consecutive_losses = 0
            return
        if outcome == "unknown_result":
            if self._limits.halt_on_unknown_order_result:
                self._halt("circuit_breaker_unknown_order_result")
            return
        if outcome == "error":
            self._consecutive_errors += 1
            if self._consecutive_errors >= self._limits.max_consecutive_errors:
                self._halt("circuit_breaker_consecutive_errors")
            return
        if outcome == "loss":
            self._consecutive_losses += 1
            if self._consecutive_losses >= self._limits.max_consecutive_losses:
                self._halt("circuit_breaker_consecutive_losses")

    def _halt(self, reason: str) -> None:
        self._kill_switch.trigger(reason)
