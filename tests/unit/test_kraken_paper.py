"""Kraken paper adapter — date publice, exec sandbox, zero chei."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from nautilus_trader.adapters.kraken.config import KrakenDataClientConfig
from nautilus_trader.adapters.sandbox.config import SandboxExecutionClientConfig

from src.engine.adapters.kraken_paper import (
    assert_no_kraken_trading_keys,
    build_kraken_data_client_config,
    build_paper_node_config,
    build_sandbox_exec_client_config,
)
from src.engine.paper_config import load_paper_trading_config

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_assert_no_keys_rejects_spot_secret() -> None:
    with pytest.raises(RuntimeError, match="forbids Kraken API keys"):
        assert_no_kraken_trading_keys({"KRAKEN_SPOT_API_SECRET": "abc"})


def test_assert_no_keys_allows_empty() -> None:
    assert_no_kraken_trading_keys({})


def test_data_client_has_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "KRAKEN_SPOT_API_KEY",
        "KRAKEN_SPOT_API_SECRET",
        "KRAKEN_FUTURES_API_KEY",
        "KRAKEN_FUTURES_API_SECRET",
        "KRAKEN_FUTURES_DEMO_API_KEY",
        "KRAKEN_FUTURES_DEMO_API_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)
    config = build_kraken_data_client_config()
    assert isinstance(config, KrakenDataClientConfig)
    assert config.api_key is None
    assert config.api_secret is None


def test_sandbox_exec_is_local_cash() -> None:
    config = build_sandbox_exec_client_config(Decimal("10000"))
    assert isinstance(config, SandboxExecutionClientConfig)
    assert config.venue == "KRAKEN"
    assert config.account_type == "CASH"
    assert "10000 USDT" in config.starting_balances


def test_paper_node_config_wires_kraken_data_and_sandbox_exec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "KRAKEN_SPOT_API_KEY",
        "KRAKEN_SPOT_API_SECRET",
        "KRAKEN_FUTURES_API_KEY",
        "KRAKEN_FUTURES_API_SECRET",
        "KRAKEN_FUTURES_DEMO_API_KEY",
        "KRAKEN_FUTURES_DEMO_API_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)
    paper = load_paper_trading_config(REPO_ROOT / "config" / "paper_trading.yaml")
    node = build_paper_node_config(paper)
    assert "KRAKEN" in node.data_clients
    assert "SANDBOX" in node.exec_clients
    data = node.data_clients["KRAKEN"]
    exec_client = node.exec_clients["SANDBOX"]
    assert getattr(data, "api_key", None) is None
    assert getattr(data, "api_secret", None) is None
    assert exec_client.venue == "KRAKEN"
