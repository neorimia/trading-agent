"""GenericSignalStrategy prin backtest_runner — semnal StrategySpec -> RiskEngine -> Nautilus."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.data.sources import CsvBarDataSource
from src.engine.backtest_runner import run_backtest
from src.engine.cost_models import VenueCostConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "bars_ethusd_1d.csv"


def _bars():
    start = datetime(2024, 11, 1, tzinfo=timezone.utc)
    end = datetime(2024, 12, 16, tzinfo=timezone.utc)
    return CsvBarDataSource(FIXTURE).fetch_bars("ETHUSD", start, end, "1d")


@pytest.mark.parametrize("kind", ["ema_cross", "donchian_breakout", "rsi_mean_reversion"])
def test_generic_adapter_runs_without_error_for_all_rule_based_kinds(
    tmp_path: Path, kind: str
) -> None:
    metrics = run_backtest(
        _bars(),
        universe_symbol="ETHUSD",
        timeframe="1d",
        strategy_kind=kind,
        costs=VenueCostConfig.for_multiplier(1),
        dataset_hash="fixture",
        halt_flag=tmp_path / "halt.flag",
    )
    assert metrics.n_bars == 45
    assert metrics.strategy == kind
    # decizii pot fi 0 dacă niciun semnal non-hold n-a apărut pe eșantion — nu e o eroare,
    # dar fiecare kind trebuie să ruleze integral prin Nautilus fără excepție.
    assert metrics.n_decisions >= 0


def test_ema_cross_via_adapter_produces_fills_matching_legacy_defaults(tmp_path: Path) -> None:
    """min_adx=0 (implicit off) + cooldown=3 pe params default -> tot produce fill-uri."""
    metrics = run_backtest(
        _bars(),
        universe_symbol="ETHUSD",
        timeframe="1d",
        strategy_kind="ema_cross",
        costs=VenueCostConfig.for_multiplier(1),
        dataset_hash="fixture",
        halt_flag=tmp_path / "halt.flag",
        strategy_params={"fast_ema_period": 10, "slow_ema_period": 20, "min_adx": "0"},
    )
    assert metrics.n_fills > 0
    assert Decimal(metrics.commissions_usdt) > 0


def test_invalid_strategy_params_raise_before_running_engine(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid params"):
        run_backtest(
            _bars(),
            universe_symbol="ETHUSD",
            timeframe="1d",
            strategy_kind="ema_cross",
            costs=VenueCostConfig.for_multiplier(1),
            dataset_hash="fixture",
            halt_flag=tmp_path / "halt.flag",
            strategy_params={"fast_ema_period": -1},
        )
