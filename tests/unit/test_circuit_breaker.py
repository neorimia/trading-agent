"""CircuitBreaker — RUNNING/HALTED; HALT persistă până la reset manual al kill switch-ului."""

from __future__ import annotations

from pathlib import Path

from src.risk.circuit_breaker import CircuitBreaker
from src.risk.config_schema import CircuitBreakerLimits
from src.risk.kill_switch import KillSwitch


def _breaker(tmp_path: Path) -> CircuitBreaker:
    limits = CircuitBreakerLimits(
        max_consecutive_errors=3,
        max_consecutive_losses=3,
        halt_on_unknown_order_result=True,
    )
    return CircuitBreaker(limits, KillSwitch(tmp_path / "halt.flag"))


def test_starts_running(tmp_path: Path) -> None:
    breaker = _breaker(tmp_path)
    assert breaker.state == "RUNNING"


def test_consecutive_errors_halt_and_write_flag(tmp_path: Path) -> None:
    breaker = _breaker(tmp_path)
    breaker.record_event("error")
    breaker.record_event("error")
    assert breaker.state == "RUNNING"
    breaker.record_event("error")
    assert breaker.state == "HALTED"
    assert breaker._kill_switch.is_active() is True


def test_success_resets_error_counter(tmp_path: Path) -> None:
    breaker = _breaker(tmp_path)
    breaker.record_event("error")
    breaker.record_event("error")
    breaker.record_event("success")
    breaker.record_event("error")
    breaker.record_event("error")
    assert breaker.state == "RUNNING"


def test_consecutive_losses_halt(tmp_path: Path) -> None:
    breaker = _breaker(tmp_path)
    breaker.record_event("loss")
    breaker.record_event("loss")
    breaker.record_event("loss")
    assert breaker.state == "HALTED"


def test_unknown_result_halts(tmp_path: Path) -> None:
    breaker = _breaker(tmp_path)
    breaker.record_event("unknown_result")
    assert breaker.state == "HALTED"


def test_stays_halted_until_manual_reset(tmp_path: Path) -> None:
    breaker = _breaker(tmp_path)
    breaker.record_event("unknown_result")
    breaker.record_event("success")
    assert breaker.state == "HALTED"
    breaker._kill_switch.reset()
    assert breaker.state == "RUNNING"
