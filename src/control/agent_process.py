"""Pornire/oprire proces paper — PID pe disc, fără acces la LLM din acest modul."""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from src.audit.audit_log import AuditLog
from src.audit.events import AuditEvent
from src.audit.postgres_store import open_audit_log, record_system_event
from src.control.runtime_state import llm_strategy_enabled, process_running, read_pid
from src.control.settings import ControlSettings
from src.execution.key_policy import (
    assert_no_kraken_trading_keys,
    has_spot_keys,
    monitor_child_env,
    paper_child_env,
    withdraw_enabled,
)
from src.monitor.broker_monitor import BrokerMonitorSnapshot, write_broker_monitor
from src.runtime_io import write_text_atomic

_CHILD_READY_S = 0.3


def _audit(settings: ControlSettings) -> AuditLog:
    return open_audit_log(
        settings.paths.audit_db,
        backend=settings.audit_store_backend,
        database_url=settings.audit_database_url,
    )


def _system_event(
    settings: ControlSettings, *, event_type: str, message: str, payload: dict | None = None
) -> None:
    """Operational (not trading) event — no-op on the files/rollback backend."""
    if settings.audit_store_backend != "postgres" or not settings.audit_database_url:
        return
    record_system_event(
        settings.audit_database_url,
        severity="info",
        component="control",
        event_type=event_type,
        message=message,
        payload=payload,
    )


class AgentProcessController(Protocol):
    def start(
        self, settings: ControlSettings, environ: dict[str, str] | None = None
    ) -> int: ...

    def stop(self, settings: ControlSettings) -> None: ...


def _stop_pid_file(pid_path) -> int | None:
    pid = read_pid(pid_path)
    if pid is not None:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    if pid_path.is_file():
        pid_path.unlink()
    return pid


def _spawn_supervised(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
    wait_s: float | None = None,
) -> subprocess.Popen[bytes]:
    timeout = _CHILD_READY_S if wait_s is None else wait_s
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("ab")
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.monotonic() + timeout
    while True:
        code = process.poll()
        if code is not None:
            handle.close()
            raise RuntimeError(
                f"child exited immediately with code {code}; see {log_path}"
            )
        if time.monotonic() >= deadline:
            return process
        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))


class SubprocessAgentProcess:
    """Pornește scripts/paper_trading/run_paper_session.py cu --operator file --mode stream."""

    def start(
        self, settings: ControlSettings, environ: dict[str, str] | None = None
    ) -> int:
        env_src = dict(os.environ if environ is None else environ)
        settings.paths.agent_pid.parent.mkdir(parents=True, exist_ok=True)
        lock_path = settings.paths.agent_pid.with_name(settings.paths.agent_pid.name + ".lock")
        with open(lock_path, "a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if process_running(settings.paths.agent_pid):
                pid = read_pid(settings.paths.agent_pid)
                if pid is not None:
                    self._ensure_monitor(settings, env_src)
                    return pid
            script = settings.paths.repo_root / "scripts" / "paper_trading" / "run_paper_session.py"
            command = [
                sys.executable,
                str(script),
                "--operator",
                "file",
                "--mode",
                "stream",
                "--runtime-dir",
                str(settings.paths.runtime_dir),
                "--config",
                str(settings.paths.paper_config),
            ]
            if not llm_strategy_enabled(settings):
                command.append("--skip-llm")
            child_env = paper_child_env(env_src)
            assert_no_kraken_trading_keys(child_env)
            process = _spawn_supervised(
                command,
                cwd=settings.paths.repo_root,
                env=child_env,
                log_path=settings.paths.runtime_dir / "logs" / "paper.log",
            )
            write_text_atomic(settings.paths.agent_pid, str(process.pid))
            _audit(settings).record(
                AuditEvent.now(
                    correlation_id=uuid4(),
                    event_type="operator_action",
                    payload={"action": "agent_start", "pid": process.pid, "mode": "stream"},
                )
            )
            _system_event(
                settings,
                event_type="agent_start",
                message=f"paper engine started (pid {process.pid})",
                payload={"pid": process.pid, "mode": "stream"},
            )
            self._ensure_monitor(settings, env_src)
            return process.pid

    def _ensure_monitor(self, settings: ControlSettings, env_src: dict[str, str]) -> None:
        snapshot = settings.paths.broker_monitor
        if not has_spot_keys(env_src):
            return
        if withdraw_enabled(env_src):
            write_broker_monitor(
                snapshot,
                BrokerMonitorSnapshot(
                    status="error",
                    error="withdraw-enabled keys are forbidden even in monitor mode",
                ),
            )
            return
        lock_path = settings.paths.broker_monitor_pid.with_name(
            settings.paths.broker_monitor_pid.name + ".lock"
        )
        settings.paths.broker_monitor_pid.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if process_running(settings.paths.broker_monitor_pid):
                return
            script = settings.paths.repo_root / "scripts" / "monitor" / "run_broker_monitor.py"
            command = [
                sys.executable,
                str(script),
                "--runtime-dir",
                str(settings.paths.runtime_dir),
            ]
            child_env = monitor_child_env(env_src)
            process = _spawn_supervised(
                command,
                cwd=settings.paths.repo_root,
                env=child_env,
                log_path=settings.paths.runtime_dir / "logs" / "monitor.log",
            )
            write_text_atomic(settings.paths.broker_monitor_pid, str(process.pid))
            _audit(settings).record(
                AuditEvent.now(
                    correlation_id=uuid4(),
                    event_type="operator_action",
                    payload={"action": "broker_monitor_start", "pid": process.pid},
                )
            )
            _system_event(
                settings,
                event_type="broker_monitor_start",
                message=f"broker monitor started (pid {process.pid})",
                payload={"pid": process.pid},
            )

    def stop(self, settings: ControlSettings) -> None:
        paper_pid = _stop_pid_file(settings.paths.agent_pid)
        monitor_pid = _stop_pid_file(settings.paths.broker_monitor_pid)
        _audit(settings).record(
            AuditEvent.now(
                correlation_id=uuid4(),
                event_type="operator_action",
                payload={
                    "action": "agent_stop",
                    "pid": paper_pid,
                    "monitor_pid": monitor_pid,
                },
            )
        )
        _system_event(
            settings,
            event_type="agent_stop",
            message=f"paper engine stop requested (pid {paper_pid})",
            payload={"pid": paper_pid, "monitor_pid": monitor_pid},
        )


class NullAgentProcess:
    """Pentru teste: scrie/șterge PID fără subprocess."""

    def __init__(self, pid: int = 4242) -> None:
        self._pid = pid

    def start(
        self, settings: ControlSettings, environ: dict[str, str] | None = None
    ) -> int:
        settings.paths.agent_pid.parent.mkdir(parents=True, exist_ok=True)
        settings.paths.agent_pid.write_text(str(self._pid), encoding="utf-8")
        return self._pid

    def stop(self, settings: ControlSettings) -> None:
        if settings.paths.agent_pid.is_file():
            settings.paths.agent_pid.unlink()
        if settings.paths.broker_monitor_pid.is_file():
            settings.paths.broker_monitor_pid.unlink()
