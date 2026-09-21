"""Metrici de backtest — win rate, expectancy, Sharpe/Sortino/Calmar, drawdown, turnover.

Pur: primește equity curve + P&L-uri de tranzacție deja calculate de `PortfolioTracker`,
nu recalculează nimic din bare. O strategie NU e „mai bună" doar pe baza total return —
de-asta `PerformanceMetrics` include explicit drawdown, Sharpe/Sortino, și `warnings`
pentru eșantioane mici sau statistici nedefinite (nu inventăm cifre).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

TIMEFRAME_BARS_PER_YEAR: dict[str, float] = {
    "1m": 365.0 * 24 * 60,
    "5m": 365.0 * 24 * 12,
    "15m": 365.0 * 24 * 4,
    "1h": 365.0 * 24,
    "4h": 365.0 * 6,
    "1d": 365.0,
}

MIN_BARS_FOR_RELIABLE_STATS = 60
MIN_TRADES_FOR_RELIABLE_STATS = 10

EquityPoint = tuple[datetime, Decimal, Decimal]  # (timestamp, equity, exposure)


def bars_per_year(timeframe: str) -> float:
    return TIMEFRAME_BARS_PER_YEAR.get(timeframe, 365.0)


def _f(value: Decimal | float) -> float:
    return float(value)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _population_stdev(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


@dataclass
class PerformanceMetrics:
    n_bars: int
    n_trades: int
    starting_equity: str
    ending_equity: str
    total_return_pct: str
    annualized_return_pct: str | None
    volatility_pct: str | None
    sharpe_ratio: str | None
    sortino_ratio: str | None
    calmar_ratio: str | None
    max_drawdown_pct: str
    recovery_factor: str | None
    win_rate: str | None
    avg_win: str | None
    avg_loss: str | None
    expectancy: str | None
    profit_factor: str | None
    longest_losing_streak: int
    turnover: str
    turnover_ratio: str | None
    total_fees: str
    estimated_slippage: str
    avg_exposure_pct: str | None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_bars": self.n_bars,
            "n_trades": self.n_trades,
            "starting_equity": self.starting_equity,
            "ending_equity": self.ending_equity,
            "total_return_pct": self.total_return_pct,
            "annualized_return_pct": self.annualized_return_pct,
            "volatility_pct": self.volatility_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "recovery_factor": self.recovery_factor,
            "win_rate": self.win_rate,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "expectancy": self.expectancy,
            "profit_factor": self.profit_factor,
            "longest_losing_streak": self.longest_losing_streak,
            "turnover": self.turnover,
            "turnover_ratio": self.turnover_ratio,
            "total_fees": self.total_fees,
            "estimated_slippage": self.estimated_slippage,
            "avg_exposure_pct": self.avg_exposure_pct,
            "warnings": list(self.warnings),
        }


def _longest_losing_streak(trades: list[float]) -> int:
    longest = 0
    current = 0
    for pnl in trades:
        if pnl < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def compute_performance_metrics(
    equity_curve: list[EquityPoint],
    closed_trades: list[Decimal],
    *,
    total_fees: Decimal,
    total_turnover: Decimal,
    starting_cash: Decimal,
    timeframe: str,
    spread_bps: Decimal | None = None,
) -> PerformanceMetrics:
    warnings: list[str] = []
    n_bars = len(equity_curve)
    trades = [_f(t) for t in closed_trades]
    n_trades = len(trades)

    if n_bars < MIN_BARS_FOR_RELIABLE_STATS:
        warnings.append(
            f"sample_too_short: only {n_bars} bars (<{MIN_BARS_FOR_RELIABLE_STATS}) — "
            "metrics below are NOT statistically reliable"
        )
    if n_trades < MIN_TRADES_FOR_RELIABLE_STATS:
        warnings.append(
            f"too_few_trades: only {n_trades} trades (<{MIN_TRADES_FOR_RELIABLE_STATS}) — "
            "win rate / profit factor / expectancy are NOT statistically meaningful"
        )

    equity_values = [_f(point[1]) for point in equity_curve]
    starting_equity = equity_values[0] if equity_values else _f(starting_cash)
    ending_equity = equity_values[-1] if equity_values else _f(starting_cash)

    total_return_pct = (
        (ending_equity / starting_equity - 1.0) * 100.0 if starting_equity > 0 else 0.0
    )

    returns: list[float] = []
    for prev, cur in zip(equity_values, equity_values[1:]):
        if prev > 0:
            returns.append(cur / prev - 1.0)

    bpy = bars_per_year(timeframe)
    annualized_return_pct: float | None = None
    if len(equity_values) > 1 and starting_equity > 0 and ending_equity > 0:
        periods = len(equity_values) - 1
        annualized_return_pct = ((ending_equity / starting_equity) ** (bpy / periods) - 1.0) * 100.0
    elif len(equity_values) > 1:
        warnings.append("annualized_return_undefined: non-positive equity encountered")

    volatility_pct: float | None = None
    sharpe_ratio: float | None = None
    if len(returns) > 1:
        ret_std = _population_stdev(returns)
        ret_mean = _mean(returns) or 0.0
        if ret_std is not None:
            volatility_pct = ret_std * math.sqrt(bpy) * 100.0
            if ret_std > 0:
                sharpe_ratio = (ret_mean / ret_std) * math.sqrt(bpy)
            else:
                warnings.append("sharpe_undefined: zero return volatility")
    else:
        warnings.append("volatility_undefined: fewer than 2 bar returns")

    sortino_ratio: float | None = None
    if returns:
        downside_sq_mean = sum(min(r, 0.0) ** 2 for r in returns) / len(returns)
        downside_dev = math.sqrt(downside_sq_mean)
        ret_mean = _mean(returns) or 0.0
        if downside_dev > 0:
            sortino_ratio = (ret_mean / downside_dev) * math.sqrt(bpy)
        else:
            warnings.append("sortino_undefined: no downside deviation (no losing bars)")

    peak = float("-inf")
    max_drawdown_frac = 0.0
    for value in equity_values:
        if value > peak:
            peak = value
        if peak > 0:
            drawdown = (peak - value) / peak
            max_drawdown_frac = max(max_drawdown_frac, drawdown)
    max_drawdown_pct = max_drawdown_frac * 100.0

    calmar_ratio: float | None = None
    if max_drawdown_frac > 0 and annualized_return_pct is not None:
        calmar_ratio = (annualized_return_pct / 100.0) / max_drawdown_frac
    elif annualized_return_pct is not None:
        warnings.append("calmar_undefined: zero max drawdown")

    recovery_factor: float | None = None
    if max_drawdown_frac > 0:
        recovery_factor = (total_return_pct / 100.0) / max_drawdown_frac
    else:
        warnings.append("recovery_factor_undefined: zero max drawdown")

    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t < 0]
    win_rate = (len(wins) / n_trades) if n_trades > 0 else None
    avg_win = _mean(wins)
    avg_loss = _mean(losses)
    expectancy = _mean(trades)
    profit_factor: float | None = None
    if losses and sum(losses) != 0:
        profit_factor = sum(wins) / abs(sum(losses))
    elif wins:
        warnings.append("profit_factor_undefined: no losing trades in sample")
    longest_losing_streak = _longest_losing_streak(trades)

    turnover = _f(total_turnover)
    turnover_ratio = turnover / _f(starting_cash) if starting_cash > 0 else None
    estimated_slippage = 0.0
    if spread_bps is not None:
        # Estimare, NU o măsurătoare directă: jumătate de spread aplicată notionalului
        # tranzacționat, presupunând fill-uri simetrice bid/ask. Documentat ca aproximare
        # în docs/backtesting-methodology.md.
        estimated_slippage = turnover * (_f(spread_bps) / 10000.0) / 2.0

    exposures = [_f(point[2]) for point in equity_curve]
    exposure_pcts = [
        (exp / eq * 100.0) for exp, eq in zip(exposures, equity_values) if eq > 0
    ]
    avg_exposure_pct = _mean(exposure_pcts)

    def _fmt(value: float | None) -> str | None:
        return None if value is None else f"{value:.6f}"

    return PerformanceMetrics(
        n_bars=n_bars,
        n_trades=n_trades,
        starting_equity=f"{starting_equity:.6f}",
        ending_equity=f"{ending_equity:.6f}",
        total_return_pct=f"{total_return_pct:.6f}",
        annualized_return_pct=_fmt(annualized_return_pct),
        volatility_pct=_fmt(volatility_pct),
        sharpe_ratio=_fmt(sharpe_ratio),
        sortino_ratio=_fmt(sortino_ratio),
        calmar_ratio=_fmt(calmar_ratio),
        max_drawdown_pct=f"{max_drawdown_pct:.6f}",
        recovery_factor=_fmt(recovery_factor),
        win_rate=_fmt(win_rate),
        avg_win=_fmt(avg_win),
        avg_loss=_fmt(avg_loss),
        expectancy=_fmt(expectancy),
        profit_factor=_fmt(profit_factor),
        longest_losing_streak=longest_losing_streak,
        turnover=f"{turnover:.6f}",
        turnover_ratio=_fmt(turnover_ratio),
        total_fees=f"{_f(total_fees):.6f}",
        estimated_slippage=f"{estimated_slippage:.6f}",
        avg_exposure_pct=_fmt(avg_exposure_pct),
        warnings=warnings,
    )


def slice_by_regime(
    equity_curve: list[EquityPoint],
    tags: list[Any],
    *,
    dimension: str,
) -> dict[str, dict[str, Any]]:
    """Grupează randamentele per-bară după `getattr(tag, dimension)` (ex: `trend`,
    `direction`, `volatility`, `volume`). Nu recalculează echitatea — doar o segmentează.
    Returnează, per bucket: n_bars, bar_win_rate (fracția de bare cu randament > 0) și
    cumulative_return_pct (randamentul compus DOAR al barelor din acel bucket, nu e
    echivalent cu „ce ai fi câștigat tranzacționând doar în acel regim" — vezi disclaimer
    în docs/backtesting-methodology.md).
    """
    if len(equity_curve) < 2 or len(tags) != len(equity_curve):
        return {}
    buckets: dict[str, list[float]] = {}
    for index in range(1, len(equity_curve)):
        prev_equity = _f(equity_curve[index - 1][1])
        cur_equity = _f(equity_curve[index][1])
        if prev_equity <= 0:
            continue
        bar_return = cur_equity / prev_equity - 1.0
        tag_value = str(getattr(tags[index], dimension, "unknown"))
        buckets.setdefault(tag_value, []).append(bar_return)

    result: dict[str, dict[str, Any]] = {}
    for bucket, rets in buckets.items():
        wins = sum(1 for r in rets if r > 0)
        compounded = 1.0
        for r in rets:
            compounded *= 1.0 + r
        result[bucket] = {
            "n_bars": len(rets),
            "bar_win_rate": f"{(wins / len(rets)):.6f}" if rets else None,
            "cumulative_return_pct": f"{(compounded - 1.0) * 100.0:.6f}",
        }
    return result
