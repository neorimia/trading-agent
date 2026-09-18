"""EMA-cross baseline: semnal pur, fără look-ahead, trece prin RiskEngine în Nautilus."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from src.data.sources import Bar, CsvBarDataSource
from src.engine.cost_models import VenueCostConfig
from src.engine.signals import baseline_proposal, ema, ema_cross_direction
from src.engine.backtest_runner import run_backtest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "bars_ethusd_1d.csv"


def test_ema_warmup_requires_full_period() -> None:
    values = [Decimal("1"), Decimal("2"), Decimal("3")]
    assert ema(values, 4) is None
    assert ema(values, 3) == Decimal("2")


def test_ema_cross_long_on_uptrend() -> None:
    closes = [Decimal(i) for i in range(1, 40)]
    assert ema_cross_direction(closes, 10, 20) == "long"


def test_baseline_proposal_none_until_slow_ema_ready() -> None:
    bars = [
        Bar(
            instrument="ETHUSD",
            timestamp=datetime(2024, 11, 1, tzinfo=timezone.utc),
            open=Decimal("1"),
            high=Decimal("1"),
            low=Decimal("1"),
            close=Decimal("1"),
            volume=Decimal("1"),
        )
    ]
    assert baseline_proposal(bars, fast_period=10, slow_period=20) is None


def test_baseline_nautilus_run_produces_fills_and_commissions(tmp_path: Path) -> None:
    start = datetime(2024, 11, 1, tzinfo=timezone.utc)
    end = datetime(2024, 12, 16, tzinfo=timezone.utc)
    bars = CsvBarDataSource(FIXTURE).fetch_bars("ETHUSD", start, end, "1d")
    metrics = run_backtest(
        bars,
        universe_symbol="ETHUSD",
        timeframe="1d",
        strategy_kind="baseline",
        costs=VenueCostConfig.for_multiplier(1),
        dataset_hash="fixture",
        halt_flag=tmp_path / "halt.flag",
    )
    assert metrics.n_bars == 45
    assert metrics.n_decisions > 0
    assert metrics.n_fills > 0
    assert Decimal(metrics.commissions_usdt) > 0


def test_higher_cost_multiplier_charges_more_commission(tmp_path: Path) -> None:
    start = datetime(2024, 11, 1, tzinfo=timezone.utc)
    end = datetime(2024, 12, 16, tzinfo=timezone.utc)
    bars = CsvBarDataSource(FIXTURE).fetch_bars("ETHUSD", start, end, "1d")
    one = run_backtest(
        bars,
        universe_symbol="ETHUSD",
        timeframe="1d",
        strategy_kind="baseline",
        costs=VenueCostConfig.for_multiplier(1),
        dataset_hash="fixture",
        halt_flag=tmp_path / "halt-1.flag",
    )
    three = run_backtest(
        bars,
        universe_symbol="ETHUSD",
        timeframe="1d",
        strategy_kind="baseline",
        costs=VenueCostConfig.for_multiplier(3),
        dataset_hash="fixture",
        halt_flag=tmp_path / "halt-3.flag",
    )
    assert Decimal(three.commissions_usdt) > Decimal(one.commissions_usdt)
