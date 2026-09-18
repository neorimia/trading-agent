"""Reproduce oficială — NautilusTrader "Backtest (Low-Level API)".

Sursă: docs/getting_started/backtest_low_level.py din repo-ul oficial
nautechsystems/nautilus_trader, la commit-ul pinned în fetch_test_data.py
(tag v1.231.0). Cod reprodus fără modificări majore — EMA cross cu execuție
TWAP pe un exchange Binance Spot simulat, folosind date istorice de trade
ticks (ETHUSDT). Zero conexiune de rețea către un broker real.

Singura modificare față de exemplul oficial: încărcarea datelor folosește
direct `CSVTickDataLoader.load()` pe fixture-ul local descărcat de
`fetch_test_data.py`, în loc de `TestDataProvider().read_csv_ticks(...)`
(care, fără un checkout local al repo-ului sursă, ar descărca aceleași
date de pe branch-ul `develop` la fiecare rulare — un target mobil,
nepotrivit pentru un raport de calificare reproductibil). Logica de
backtest propriu-zisă e identică cu exemplul oficial.

Rulare: python -m scripts.nautilus_qualification.run_backtest
"""

from __future__ import annotations

from decimal import Decimal

from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.examples.algorithms.twap import TWAPExecAlgorithm
from nautilus_trader.examples.strategies.ema_cross_twap import EMACrossTWAP
from nautilus_trader.examples.strategies.ema_cross_twap import EMACrossTWAPConfig
from nautilus_trader.model import BarType
from nautilus_trader.model import Money
from nautilus_trader.model import TraderId
from nautilus_trader.model import Venue
from nautilus_trader.model.currencies import ETH
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import OmsType
from nautilus_trader.persistence.loaders import CSVTickDataLoader
from nautilus_trader.persistence.wranglers import TradeTickDataWrangler
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from scripts.nautilus_qualification.fetch_test_data import fetch_test_data


def run() -> BacktestEngine:
    # --- Load data (adaptare: fixture local pinned, vezi docstring de mai sus) ---
    csv_path = fetch_test_data()
    trades_df = CSVTickDataLoader.load(file_path=csv_path)

    ETHUSDT_BINANCE = TestInstrumentProvider.ethusdt_binance()

    wrangler = TradeTickDataWrangler(instrument=ETHUSDT_BINANCE)
    ticks = wrangler.process(trades_df)

    # --- Initialize the engine (identic cu exemplul oficial) ---
    config = BacktestEngineConfig(trader_id=TraderId("BACKTESTER-001"))
    engine = BacktestEngine(config=config)

    # --- Add a venue ---
    BINANCE = Venue("BINANCE")
    engine.add_venue(
        venue=BINANCE,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        base_currency=None,
        starting_balances=[Money(1_000_000.0, USDT), Money(10.0, ETH)],
    )

    # --- Add data ---
    engine.add_instrument(ETHUSDT_BINANCE)
    engine.add_data(ticks)

    # --- Add strategy ---
    strategy_config = EMACrossTWAPConfig(
        instrument_id=ETHUSDT_BINANCE.id,
        bar_type=BarType.from_str("ETHUSDT.BINANCE-250-TICK-LAST-INTERNAL"),
        trade_size=Decimal("0.10"),
        fast_ema_period=10,
        slow_ema_period=20,
        twap_horizon_secs=10.0,
        twap_interval_secs=2.5,
    )
    strategy = EMACrossTWAP(config=strategy_config)
    engine.add_strategy(strategy=strategy)

    # --- Add execution algorithm ---
    exec_algorithm = TWAPExecAlgorithm()
    engine.add_exec_algorithm(exec_algorithm)

    # --- Run ---
    engine.run()

    # --- Post-run reports ---
    account_report = engine.trader.generate_account_report(BINANCE)
    fills_report = engine.trader.generate_order_fills_report()
    positions_report = engine.trader.generate_positions_report()

    print("=== ACCOUNT REPORT ===")
    print(account_report.to_string())
    print("\n=== ORDER FILLS REPORT ===")
    print(fills_report.to_string())
    print("\n=== POSITIONS REPORT ===")
    print(positions_report.to_string())

    engine.dispose()
    return engine


if __name__ == "__main__":
    run()
