"""Launcher env isolation: LLM/research children never inherit exchange keys."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.dev.start_stack import (
    assert_paper_start_allowed,
    isolated_service_env,
    live_flag_enabled,
    read_dotenv_value,
)


def test_isolated_service_env_strips_broker_and_live_flag() -> None:
    source = {
        "PATH": "/usr/bin",
        "HOME": "/tmp",
        "KRAKEN_SPOT_API_KEY": "spot-key",
        "KRAKEN_SPOT_API_SECRET": "spot-secret",
        "KRAKEN_FUTURES_API_KEY": "fx-key",
        "LIVE_TRADING_ENABLED": "true",
        "BROKER_API_KEY": "broker-key",
        "BROKER_API_SECRET": "broker-secret",
        "BROKER_PAPER_MODE": "true",
        "BROKER_NAME": "KRAKEN",
        "BROKER_ACCOUNT_ID": "acct",
        "OLLAMA_HOST": "http://127.0.0.1:11434",
    }
    env = isolated_service_env(source)
    assert env["PATH"] == "/usr/bin"
    assert env["OLLAMA_HOST"] == "http://127.0.0.1:11434"
    assert "KRAKEN_SPOT_API_KEY" not in env
    assert "KRAKEN_SPOT_API_SECRET" not in env
    assert "KRAKEN_FUTURES_API_KEY" not in env
    assert "LIVE_TRADING_ENABLED" not in env
    assert "BROKER_API_KEY" not in env
    assert "BROKER_API_SECRET" not in env
    assert "BROKER_PAPER_MODE" not in env
    assert "BROKER_NAME" not in env
    assert "BROKER_ACCOUNT_ID" not in env


def test_read_dotenv_value_ignores_comments(tmp_path: Path) -> None:
    path = tmp_path / ".env.control"
    path.write_text(
        "# CONTROL_OPERATOR_TOKEN=from-comment\n"
        "CONTROL_OPERATOR_TOKEN=real-token\n",
        encoding="utf-8",
    )
    assert read_dotenv_value(path, "CONTROL_OPERATOR_TOKEN") == "real-token"
    assert read_dotenv_value(path, "MISSING") == ""
    assert read_dotenv_value(tmp_path / "nope", "CONTROL_OPERATOR_TOKEN") == ""


def test_live_flag_reads_engine_file_when_unset(tmp_path: Path) -> None:
    (tmp_path / ".env.engine").write_text("LIVE_TRADING_ENABLED=true\n", encoding="utf-8")
    assert live_flag_enabled(tmp_path, {}) is True
    with pytest.raises(SystemExit, match="paper start is blocked"):
        assert_paper_start_allowed(tmp_path, {})


def test_live_flag_process_env_wins_over_file(tmp_path: Path) -> None:
    (tmp_path / ".env.engine").write_text("LIVE_TRADING_ENABLED=true\n", encoding="utf-8")
    assert live_flag_enabled(tmp_path, {"LIVE_TRADING_ENABLED": "false"}) is False
    assert_paper_start_allowed(tmp_path, {"LIVE_TRADING_ENABLED": "false"})
