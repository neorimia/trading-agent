"""run_backtest expune performance/baselines/regime în `metrics.extra`, end-to-end."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.data.sources import CsvBarDataSource
from src.engine.backtest_runner import run_backtest
from src.engine.cost_models import VenueCostConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "bars_ethusd_1d.csv"


def _bars():
    return CsvBarDataSource(FIXTURE).fetch_bars(
        "ETHUSD",
        datetime(2024, 11, 1, tzinfo=timezone.utc),
        datetime(2024, 12, 16, tzinfo=timezone.utc),
        "1d",
    )


def test_backtest_extra_contains_performance_baselines_and_regime(tmp_path: Path) -> None:
    metrics = run_backtest(
        _bars(),
        universe_symbol="ETHUSD",
        timeframe="1d",
        strategy_kind="baseline",
        costs=VenueCostConfig.for_multiplier(1),
        dataset_hash="fixture",
        halt_flag=tmp_path / "halt.flag",
    )
    assert "performance" in metrics.extra
    perf = metrics.extra["performance"]
    assert perf["n_bars"] == 45
    assert any("sample_too_short" in w for w in perf["warnings"])

    assert "baselines" in metrics.extra
    baselines = metrics.extra["baselines"]
    assert baselines["cash_pct"] == "0"
    assert baselines["buy_and_hold_pct"] is not None

    assert "regime" in metrics.extra
    regime = metrics.extra["regime"]
    for dimension in ("trend", "direction", "volatility", "volume", "shock"):
        assert dimension in regime

    assert len(metrics.extra["equity_curve"]) == 45
    assert len(metrics.extra["drawdown_curve"]) == 45
    assert len(metrics.extra["buy_and_hold_curve"]) == 45
    assert isinstance(metrics.extra["trade_pnls"], list)
    first_point = metrics.extra["equity_curve"][0]
    assert "t" in first_point and "equity" in first_point and "exposure" in first_point


def test_backtest_extra_is_deterministic_across_runs(tmp_path: Path) -> None:
    bars = _bars()
    kwargs = dict(
        universe_symbol="ETHUSD",
        timeframe="1d",
        strategy_kind="ema_cross",
        costs=VenueCostConfig.for_multiplier(1),
        dataset_hash="fixture",
    )
    first = run_backtest(bars, halt_flag=tmp_path / "halt-1.flag", **kwargs)
    second = run_backtest(bars, halt_flag=tmp_path / "halt-2.flag", **kwargs)
    assert first.extra == second.extra
