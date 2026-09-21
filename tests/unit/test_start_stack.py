"""Launcher env isolation: LLM/research children never inherit exchange keys."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.dev.start_stack import (
    _DEFAULT_POSTGRES_URL,
    assert_paper_start_allowed,
    isolated_service_env,
    live_flag_enabled,
    postgres_backend_enabled,
    postgres_database_urls,
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


def test_postgres_backend_enabled_from_research_or_control(tmp_path: Path) -> None:
    assert postgres_backend_enabled(tmp_path) is False
    (tmp_path / ".env.research").write_text(
        "RESEARCH_STORE_BACKEND=postgres\n", encoding="utf-8"
    )
    assert postgres_backend_enabled(tmp_path) is True
    (tmp_path / ".env.research").write_text(
        "RESEARCH_STORE_BACKEND=sqlite\n", encoding="utf-8"
    )
    (tmp_path / ".env.control").write_text(
        "RESEARCH_STORE_BACKEND=postgres\n", encoding="utf-8"
    )
    assert postgres_backend_enabled(tmp_path) is True


def test_postgres_database_urls_collects_research_and_control(tmp_path: Path) -> None:
    (tmp_path / ".env.research").write_text(
        "RESEARCH_STORE_BACKEND=postgres\n"
        "RESEARCH_DATABASE_URL=postgresql://writer@127.0.0.1:5432/trading_research\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.control").write_text(
        "RESEARCH_STORE_BACKEND=postgres\n"
        "CONTROL_DATABASE_URL=postgresql://reader@127.0.0.1:5432/trading_research\n",
        encoding="utf-8",
    )
    urls = postgres_database_urls(tmp_path)
    assert urls == [
        "postgresql://writer@127.0.0.1:5432/trading_research",
        "postgresql://reader@127.0.0.1:5432/trading_research",
    ]


def test_postgres_database_urls_default_when_backend_without_url(tmp_path: Path) -> None:
    (tmp_path / ".env.research").write_text(
        "RESEARCH_STORE_BACKEND=postgres\n", encoding="utf-8"
    )
    assert postgres_database_urls(tmp_path) == [_DEFAULT_POSTGRES_URL]


def test_postgres_backend_enabled_from_market_data_engine_file(tmp_path: Path) -> None:
    assert postgres_backend_enabled(tmp_path) is False
    (tmp_path / ".env.engine").write_text(
        "MARKET_DATA_STORE_BACKEND=postgres\n", encoding="utf-8"
    )
    assert postgres_backend_enabled(tmp_path) is True


def test_postgres_database_urls_includes_market_data_engine_url(tmp_path: Path) -> None:
    (tmp_path / ".env.engine").write_text(
        "MARKET_DATA_STORE_BACKEND=postgres\n"
        "MARKET_DATA_DATABASE_URL=postgresql://market_data_writer@127.0.0.1:5432/trading_research\n",
        encoding="utf-8",
    )
    assert postgres_database_urls(tmp_path) == [
        "postgresql://market_data_writer@127.0.0.1:5432/trading_research"
    ]
