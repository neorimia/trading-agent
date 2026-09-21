"""PerformanceMetrics — cifre cunoscute, calculate manual, nu doar "rulează fără erori"."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.engine.metrics import (
    PerformanceMetrics,
    bars_per_year,
    compute_performance_metrics,
    slice_by_regime,
)

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _curve(equities: list[str], exposures: list[str] | None = None) -> list:
    exposures = exposures or ["0"] * len(equities)
    return [
        (START + timedelta(days=i), Decimal(e), Decimal(x))
        for i, (e, x) in enumerate(zip(equities, exposures))
    ]


def test_total_return_and_drawdown_are_exact() -> None:
    # 100 -> 110 -> 99 -> 121 : total return = +21%, max drawdown from 110 to 99 = 10%
    curve = _curve(["100", "110", "99", "121"])
    result = compute_performance_metrics(
        curve,
        closed_trades=[],
        total_fees=Decimal("0"),
        total_turnover=Decimal("0"),
        starting_cash=Decimal("100"),
        timeframe="1d",
    )
    assert result.n_bars == 4
    assert math.isclose(float(result.total_return_pct), 21.0, abs_tol=1e-6)
    assert math.isclose(float(result.max_drawdown_pct), 10.0, abs_tol=1e-6)


def test_win_rate_expectancy_profit_factor_from_closed_trades() -> None:
    curve = _curve(["100", "105", "110"])
    trades = [Decimal("10"), Decimal("-5"), Decimal("20"), Decimal("-5")]
    result = compute_performance_metrics(
        curve,
        closed_trades=trades,
        total_fees=Decimal("1"),
        total_turnover=Decimal("1000"),
        starting_cash=Decimal("100"),
        timeframe="1d",
    )
    assert result.n_trades == 4
    assert math.isclose(float(result.win_rate), 0.5, abs_tol=1e-9)
    assert math.isclose(float(result.avg_win), 15.0, abs_tol=1e-9)
    assert math.isclose(float(result.avg_loss), -5.0, abs_tol=1e-9)
    assert math.isclose(float(result.expectancy), 5.0, abs_tol=1e-9)
    # profit_factor = sum(wins)/abs(sum(losses)) = 30/10 = 3
    assert math.isclose(float(result.profit_factor), 3.0, abs_tol=1e-9)


def test_longest_losing_streak_counts_consecutive_negative_trades() -> None:
    curve = _curve(["100", "100"])
    trades = [Decimal("1"), Decimal("-1"), Decimal("-1"), Decimal("-1"), Decimal("2"), Decimal("-1")]
    result = compute_performance_metrics(
        curve,
        closed_trades=trades,
        total_fees=Decimal("0"),
        total_turnover=Decimal("0"),
        starting_cash=Decimal("100"),
        timeframe="1d",
    )
    assert result.longest_losing_streak == 3


def test_short_sample_and_too_few_trades_trigger_warnings() -> None:
    curve = _curve(["100", "101"])
    result = compute_performance_metrics(
        curve,
        closed_trades=[Decimal("1")],
        total_fees=Decimal("0"),
        total_turnover=Decimal("0"),
        starting_cash=Decimal("100"),
        timeframe="1d",
    )
    assert any("sample_too_short" in w for w in result.warnings)
    assert any("too_few_trades" in w for w in result.warnings)


def test_profit_factor_undefined_when_no_losing_trades() -> None:
    curve = _curve(["100", "110"])
    result = compute_performance_metrics(
        curve,
        closed_trades=[Decimal("5"), Decimal("5")],
        total_fees=Decimal("0"),
        total_turnover=Decimal("0"),
        starting_cash=Decimal("100"),
        timeframe="1d",
    )
    assert result.profit_factor is None
    assert any("profit_factor_undefined" in w for w in result.warnings)


def test_empty_equity_curve_does_not_crash() -> None:
    result = compute_performance_metrics(
        [],
        closed_trades=[],
        total_fees=Decimal("0"),
        total_turnover=Decimal("0"),
        starting_cash=Decimal("100"),
        timeframe="1d",
    )
    assert result.n_bars == 0
    assert result.n_trades == 0


def test_bars_per_year_known_and_unknown_timeframe() -> None:
    assert bars_per_year("1d") == 365.0
    assert bars_per_year("does-not-exist") == 365.0
    assert bars_per_year("1h") == 365.0 * 24


def test_estimated_slippage_scales_with_turnover_and_spread() -> None:
    curve = _curve(["100", "100"])
    result = compute_performance_metrics(
        curve,
        closed_trades=[],
        total_fees=Decimal("0"),
        total_turnover=Decimal("10000"),
        starting_cash=Decimal("100"),
        timeframe="1d",
        spread_bps=Decimal("20"),
    )
    # 10000 * (20/10000) / 2 = 10
    assert math.isclose(float(result.estimated_slippage), 10.0, abs_tol=1e-9)


def test_avg_exposure_pct_is_mean_of_per_bar_ratio() -> None:
    curve = _curve(["100", "100", "100"], exposures=["0", "50", "100"])
    result = compute_performance_metrics(
        curve,
        closed_trades=[],
        total_fees=Decimal("0"),
        total_turnover=Decimal("0"),
        starting_cash=Decimal("100"),
        timeframe="1d",
    )
    # exposure ratios: 0%, 50%, 100% -> mean 50%
    assert math.isclose(float(result.avg_exposure_pct), 50.0, abs_tol=1e-9)


class _Tag:
    def __init__(self, **kwargs) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_slice_by_regime_groups_bar_returns_by_dimension() -> None:
    curve = _curve(["100", "110", "99", "108.9"])
    tags = [
        _Tag(trend="unknown"),
        _Tag(trend="trend"),
        _Tag(trend="range"),
        _Tag(trend="trend"),
    ]
    result = slice_by_regime(curve, tags, dimension="trend")
    # bar returns: idx1 (trend): +10%, idx2 (range): -10%, idx3 (trend): +10%
    assert result["trend"]["n_bars"] == 2
    assert math.isclose(float(result["trend"]["bar_win_rate"]), 1.0, abs_tol=1e-9)
    assert result["range"]["n_bars"] == 1
    assert math.isclose(float(result["range"]["bar_win_rate"]), 0.0, abs_tol=1e-9)
