"""Cale B: date publice Kraken + execuție sandbox Nautilus. Zero chei de trading."""

from __future__ import annotations

from decimal import Decimal

from nautilus_trader.adapters.kraken.config import KrakenDataClientConfig
from nautilus_trader.adapters.sandbox.config import SandboxExecutionClientConfig
from nautilus_trader.live.config import TradingNodeConfig

from src.engine.paper_config import PaperTradingConfig
from src.execution.key_policy import assert_no_kraken_trading_keys


def build_kraken_data_client_config() -> KrakenDataClientConfig:
    """Client de date Spot, fără credențiale — feed public."""
    assert_no_kraken_trading_keys()
    return KrakenDataClientConfig(api_key=None, api_secret=None)


def build_sandbox_exec_client_config(starting_cash: Decimal) -> SandboxExecutionClientConfig:
    """Execuție simulată locală. Niciun ordin nu ajunge la Kraken."""
    cash = format(starting_cash, "f")
    return SandboxExecutionClientConfig(
        venue="KRAKEN",
        starting_balances=[f"{cash} USDT"],
        base_currency="USDT",
        account_type="CASH",
        oms_type="NETTING",
        default_leverage=Decimal(1),
    )


def build_paper_node_config(config: PaperTradingConfig) -> TradingNodeConfig:
    if not config.dry_run:
        raise ValueError("live execution is forbidden in Faza 5")
    if config.venue != "KRAKEN":
        raise ValueError("Path B requires venue=KRAKEN")
    return TradingNodeConfig(
        trader_id="PAPER-001",
        data_clients={"KRAKEN": build_kraken_data_client_config()},
        exec_clients={"SANDBOX": build_sandbox_exec_client_config(config.starting_cash)},
    )
