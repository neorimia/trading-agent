"""CLI paper session: build_loop must construct without a NameError."""

from __future__ import annotations

from pathlib import Path

from scripts.paper_trading.run_paper_session import BaselineProposalClient, build_loop
from src.engine.paper_config import load_paper_trading_config
from src.engine.strategy_paper import PaperTradingLoop
from src.execution.broker import SimulatedBroker

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_build_loop_constructs_without_network(tmp_path: Path) -> None:
    config = load_paper_trading_config(REPO_ROOT / "config" / "paper_trading.yaml")
    client = BaselineProposalClient(
        fast_period=config.fast_ema_period,
        slow_period=config.slow_ema_period,
    )
    loop, broker = build_loop(tmp_path, config, client, None)
    assert isinstance(loop, PaperTradingLoop)
    assert isinstance(broker, SimulatedBroker)
    assert (tmp_path / "audit" / "audit.sqlite").is_file()
