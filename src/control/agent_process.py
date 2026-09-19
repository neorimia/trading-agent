"""Pornire/oprire proces paper — PID pe disc, fără acces la LLM din acest modul."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from typing import Protocol
from uuid import uuid4

from src.audit.audit_log import AuditLog
from src.audit.events import AuditEvent
from src.control.runtime_state import llm_strategy_enabled, process_running, read_pid
from src.control.settings import ControlSettings


class AgentProcessController(Protocol):
    def start(self, settings: ControlSettings) -> int: ...

    def stop(self, settings: ControlSettings) -> None: ...


class SubprocessAgentProcess:
    """Pornește scripts/paper_trading/run_paper_session.py cu --operator file."""

    def start(self, settings: ControlSettings) -> int:
        if process_running(settings.paths.agent_pid):
            pid = read_pid(settings.paths.agent_pid)
            if pid is not None:
                return pid
        settings.paths.agent_pid.parent.mkdir(parents=True, exist_ok=True)
        script = settings.paths.repo_root / "scripts" / "paper_trading" / "run_paper_session.py"
        command = [
            sys.executable,
            str(script),
            "--operator",
            "file",
            "--runtime-dir",
            str(settings.paths.runtime_dir),
            "--config",
            str(settings.paths.paper_config),
        ]
        if not llm_strategy_enabled(settings):
            command.append("--skip-llm")
        process = subprocess.Popen(
            command,
            cwd=str(settings.paths.repo_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        settings.paths.agent_pid.write_text(str(process.pid), encoding="utf-8")
        AuditLog(settings.paths.audit_db).record(
            AuditEvent.now(
                correlation_id=uuid4(),
                event_type="operator_action",
                payload={"action": "agent_start", "pid": process.pid},
            )
        )
        return process.pid

    def stop(self, settings: ControlSettings) -> None:
        pid = read_pid(settings.paths.agent_pid)
        if pid is not None:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        if settings.paths.agent_pid.is_file():
            settings.paths.agent_pid.unlink()
        AuditLog(settings.paths.audit_db).record(
            AuditEvent.now(
                correlation_id=uuid4(),
                event_type="operator_action",
                payload={"action": "agent_stop", "pid": pid},
            )
        )


class NullAgentProcess:
    """Pentru teste: scrie/șterge PID fără subprocess."""

    def __init__(self, pid: int = 4242) -> None:
        self._pid = pid

    def start(self, settings: ControlSettings) -> int:
        settings.paths.agent_pid.parent.mkdir(parents=True, exist_ok=True)
        settings.paths.agent_pid.write_text(str(self._pid), encoding="utf-8")
        return self._pid

    def stop(self, settings: ControlSettings) -> None:
        if settings.paths.agent_pid.is_file():
            settings.paths.agent_pid.unlink()
