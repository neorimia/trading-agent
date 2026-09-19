"""Paper-engine subprocess start: sanitized env, stream mode, optional monitor sidecar."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.control.agent_process import SubprocessAgentProcess
from src.control.runtime_state import pid_is_alive
from src.control.settings import load_control_settings
from src.monitor.broker_monitor import load_broker_monitor

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _fast_child_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.control.agent_process._CHILD_READY_S", 0.0)


def _settings(tmp_path: Path):
    runtime = tmp_path / "runtime"
    environ = {
        "CONTROL_SERVER_HOST": "127.0.0.1",
        "RUNTIME_DIR": str(runtime),
        "HALT_FLAG_PATH": str(runtime / "control" / "halt.flag"),
        "RISK_LIMITS_PATH": str(REPO_ROOT / "config" / "risk_limits.yaml"),
        "UNIVERSE_PATH": str(REPO_ROOT / "config" / "universe.yaml"),
        "PAPER_CONFIG_PATH": str(REPO_ROOT / "config" / "paper_trading.yaml"),
        "STRATEGIES_PATH": str(REPO_ROOT / "config" / "strategies.yaml"),
        "LIVE_TRADING_ENABLED": "false",
        "BROKER_PAPER_MODE": "true",
        "ENVIRONMENT": "test",
    }
    return load_control_settings(root=tmp_path, environ=environ)


def _alive_proc(pid: int) -> MagicMock:
    proc = MagicMock()
    proc.pid = pid
    proc.poll.return_value = None
    return proc


def test_start_passes_sanitized_env_and_stream_mode(tmp_path: Path, monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_popen(command, **kwargs):  # noqa: ANN001, ANN003
        calls.append({"command": command, "env": kwargs.get("env")})
        return _alive_proc(91000 + len(calls))

    monkeypatch.setattr("src.control.agent_process.subprocess.Popen", fake_popen)
    settings = _settings(tmp_path)
    environ = {
        "PATH": "/usr/bin",
        "KRAKEN_SPOT_API_KEY": "live-key",
        "KRAKEN_SPOT_API_SECRET": "live-secret",
        "KRAKEN_FUTURES_API_KEY": "fx-key",
        "BROKER_API_KEY": "broker-key",
        "KRAKEN_KEY_WITHDRAW_ENABLED": "false",
    }
    pid = SubprocessAgentProcess().start(settings, environ)
    assert pid == 91001
    assert len(calls) == 2
    paper = calls[0]
    monitor = calls[1]
    paper_cmd = paper["command"]
    assert isinstance(paper_cmd, list)
    assert "--mode" in paper_cmd
    assert paper_cmd[paper_cmd.index("--mode") + 1] == "stream"
    assert "run_paper_session.py" in str(paper_cmd)
    paper_env = paper["env"]
    assert isinstance(paper_env, dict)
    assert "KRAKEN_SPOT_API_KEY" not in paper_env
    assert "KRAKEN_SPOT_API_SECRET" not in paper_env
    assert "BROKER_API_KEY" not in paper_env
    monitor_cmd = monitor["command"]
    assert isinstance(monitor_cmd, list)
    assert "run_broker_monitor.py" in str(monitor_cmd)
    monitor_env = monitor["env"]
    assert isinstance(monitor_env, dict)
    assert monitor_env["KRAKEN_SPOT_API_KEY"] == "live-key"
    assert "KRAKEN_FUTURES_API_KEY" not in monitor_env
    assert settings.paths.agent_pid.read_text(encoding="utf-8") == "91001"
    assert settings.paths.broker_monitor_pid.read_text(encoding="utf-8") == "91002"


def test_start_without_keys_skips_monitor(tmp_path: Path, monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_popen(command, **kwargs):  # noqa: ANN001, ANN003
        calls.append(command)
        return _alive_proc(70001)

    monkeypatch.setattr("src.control.agent_process.subprocess.Popen", fake_popen)
    settings = _settings(tmp_path)
    SubprocessAgentProcess().start(settings, {"PATH": "/usr/bin"})
    assert len(calls) == 1
    assert "run_paper_session.py" in str(calls[0])
    assert not settings.paths.broker_monitor_pid.is_file()


def test_withdraw_enabled_does_not_spawn_monitor(tmp_path: Path, monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_popen(command, **kwargs):  # noqa: ANN001, ANN003
        calls.append(command)
        return _alive_proc(70002)

    monkeypatch.setattr("src.control.agent_process.subprocess.Popen", fake_popen)
    settings = _settings(tmp_path)
    SubprocessAgentProcess().start(
        settings,
        {
            "KRAKEN_SPOT_API_KEY": "k",
            "KRAKEN_SPOT_API_SECRET": "s",
            "KRAKEN_KEY_WITHDRAW_ENABLED": "true",
        },
    )
    assert len(calls) == 1
    snap = load_broker_monitor(settings.paths.broker_monitor)
    assert snap.status == "error"
    assert snap.error is not None
    assert "withdraw" in snap.error


def test_concurrent_start_spawns_once(tmp_path: Path, monkeypatch) -> None:
    pids: list[int] = []

    def fake_popen(command, **kwargs):  # noqa: ANN001, ANN003
        time.sleep(0.05)
        proc = _alive_proc(80000 + len(pids))
        pids.append(proc.pid)
        return proc

    monkeypatch.setattr("src.control.agent_process.subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        "src.control.agent_process.process_running",
        lambda path: path.is_file() and path.read_text(encoding="utf-8").strip().isdigit(),
    )
    settings = _settings(tmp_path)
    controller = SubprocessAgentProcess()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(controller.start, settings, {"PATH": "/usr/bin"})
        second = pool.submit(controller.start, settings, {"PATH": "/usr/bin"})
        results = {first.result(), second.result()}
    assert len(pids) == 1
    assert results == {pids[0]}
    assert settings.paths.agent_pid.read_text(encoding="utf-8") == str(pids[0])


def test_start_fails_if_paper_exits_immediately(tmp_path: Path, monkeypatch) -> None:
    def fake_popen(command, **kwargs):  # noqa: ANN001, ANN003
        proc = MagicMock()
        proc.pid = 42
        proc.poll.return_value = 1
        return proc

    monkeypatch.setattr("src.control.agent_process.subprocess.Popen", fake_popen)
    settings = _settings(tmp_path)
    with pytest.raises(RuntimeError, match="exited immediately"):
        SubprocessAgentProcess().start(settings, {"PATH": "/usr/bin"})
    assert not settings.paths.agent_pid.is_file()
    assert (settings.paths.runtime_dir / "logs" / "paper.log").is_file()


def test_pid_is_alive_false_for_zombie(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.control.runtime_state._pid_is_zombie", lambda pid: True)
    monkeypatch.setattr("src.control.runtime_state.os.kill", lambda pid, sig: None)
    assert pid_is_alive(123) is False


def test_pid_is_alive_true_when_not_zombie(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.control.runtime_state._pid_is_zombie", lambda pid: False)
    monkeypatch.setattr("src.control.runtime_state.os.kill", lambda pid, sig: None)
    assert pid_is_alive(123) is True


def test_pid_is_zombie_reads_ps_state(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.control.runtime_state import _pid_is_zombie

    class Result:
        stdout = "Z\n"

    monkeypatch.setattr(
        "src.control.runtime_state.subprocess.run",
        lambda *args, **kwargs: Result(),
    )
    assert _pid_is_zombie(9) is True
    Result.stdout = "S\n"
    assert _pid_is_zombie(9) is False
