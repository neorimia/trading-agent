"""Harness NautilusTrader: date OHLCV + quote bid/ask, comisioane, slippage, strategii."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import numpy as np
from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import LoggingConfig
from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.wranglers import BarDataWrangler, QuoteTickDataWrangler

from src.data.sources import Bar
from src.engine import baselines
from src.engine import metrics as backtest_metrics
from src.engine import regime as regime_mod
from src.engine.cost_models import VenueCostConfig, build_fee_model, build_fill_model
from src.engine.instruments import NAUTILUS_VENUE, make_spot_instrument, nautilus_symbol
from src.engine.portfolio_tracker import PortfolioTracker
from src.engine.proposal_cache import ProposalClient
from src.engine.research_client import ResearchClient
from src.engine.strategy_adapter import GenericSignalStrategy, GenericSignalStrategyConfig
from src.engine.strategy_baseline import BaselineEMACross, BaselineEMACrossConfig
from src.engine.strategy_llm_assisted import LLMAssistedStrategy, LLMAssistedStrategyConfig
from src.engine.strategy_registry import RULE_BASED_KINDS, default_params_for_kind
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.config_schema import load_risk_limits
from src.risk.kill_switch import KillSwitch
from src.risk.portfolio_state import load_instrument_rules
from src.risk.risk_engine import RiskEngine

REGIME_DIMENSIONS = ("trend", "direction", "volatility", "volume", "shock")

BAR_SPEC = {
    "1m": "1-MINUTE",
    "5m": "5-MINUTE",
    "15m": "15-MINUTE",
    "1h": "1-HOUR",
    "4h": "4-HOUR",
    "1d": "1-DAY",
}

StrategyKind = Literal[
    "baseline", "llm", "ema_cross", "donchian_breakout", "rsi_mean_reversion"
]
# Kind-uri rulate prin adaptorul generic (StrategySpec), nu prin clase Nautilus dedicate.
GENERIC_SPEC_KINDS = frozenset(RULE_BASED_KINDS)
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STARTING_USDT = Decimal("10000")
DEFAULT_FAST_EMA = 10
DEFAULT_SLOW_EMA = 20
DEFAULT_LOOKBACK = 20


@dataclass
class BacktestMetrics:
    strategy: str
    cost_multiplier: int
    dataset_hash: str
    n_bars: int
    n_fills: int
    n_decisions: int
    ending_usdt: str
    commissions_usdt: str
    decisions: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def comparable(self) -> dict[str, Any]:
        """Câmpuri stabile între rulări (fără UUID/wall-clock)."""
        return {
            "strategy": self.strategy,
            "cost_multiplier": self.cost_multiplier,
            "dataset_hash": self.dataset_hash,
            "n_bars": self.n_bars,
            "n_fills": self.n_fills,
            "n_decisions": self.n_decisions,
            "ending_usdt": self.ending_usdt,
            "commissions_usdt": self.commissions_usdt,
            "decisions": self.decisions,
        }


def _bar_type(universe_symbol: str, timeframe: str) -> BarType:
    spec = BAR_SPEC.get(timeframe)
    if spec is None:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    return BarType.from_str(
        f"{nautilus_symbol(universe_symbol)}.{NAUTILUS_VENUE.value}-{spec}-LAST-EXTERNAL"
    )


def _writable_frame(data: dict[str, list[float]], index: pd.DatetimeIndex) -> pd.DataFrame:
    frame = pd.DataFrame(data, index=index)
    for column in frame.columns:
        frame[column] = np.array(frame[column].to_numpy(copy=True), dtype="float64")
    return frame


def _bars_frame(bars: list[Bar]) -> pd.DataFrame:
    index = pd.DatetimeIndex([bar.timestamp for bar in bars], tz="UTC", name="timestamp")
    return _writable_frame(
        {
            "open": [float(bar.open) for bar in bars],
            "high": [float(bar.high) for bar in bars],
            "low": [float(bar.low) for bar in bars],
            "close": [float(bar.close) for bar in bars],
            "volume": [float(bar.volume) for bar in bars],
        },
        index,
    )


def _quotes_frame(bars: list[Bar], spread_bps: Decimal) -> pd.DataFrame:
    half = (spread_bps / Decimal("10000")) / Decimal("2")
    index = pd.DatetimeIndex([bar.timestamp for bar in bars], tz="UTC", name="timestamp")
    return _writable_frame(
        {
            "bid_price": [float(bar.close * (Decimal("1") - half)) for bar in bars],
            "ask_price": [float(bar.close * (Decimal("1") + half)) for bar in bars],
        },
        index,
    )


def _trade_start_ns(bars: list[Bar], trade_start: datetime | None) -> int:
    if trade_start is None:
        return 0
    return int(dt_to_unix_nanos(trade_start))


def build_risk_stack(halt_flag: Path) -> tuple[RiskEngine, CircuitBreaker, KillSwitch]:
    limits = load_risk_limits(REPO_ROOT / "config" / "risk_limits.yaml")
    rules, classes = load_instrument_rules(REPO_ROOT / "config" / "universe.yaml")
    kill_switch = KillSwitch(halt_flag)
    breaker = CircuitBreaker(limits.circuit_breaker, kill_switch)
    engine = RiskEngine(limits, rules, classes, kill_switch)
    return engine, breaker, kill_switch


def run_backtest(
    bars: list[Bar],
    *,
    universe_symbol: str,
    timeframe: str,
    strategy_kind: StrategyKind,
    costs: VenueCostConfig,
    dataset_hash: str,
    halt_flag: Path,
    log_level: str = "ERROR",
    trade_start: datetime | None = None,
    proposal_client: ProposalClient | None = None,
    research_client: ResearchClient | None = None,
    starting_usdt: Decimal = DEFAULT_STARTING_USDT,
    fast_ema_period: int = DEFAULT_FAST_EMA,
    slow_ema_period: int = DEFAULT_SLOW_EMA,
    lookback_bars: int = DEFAULT_LOOKBACK,
    strategy_params: dict[str, object] | None = None,
) -> BacktestMetrics:
    if not bars:
        raise ValueError("cannot backtest an empty series")
    if strategy_kind == "llm" and proposal_client is None:
        raise ValueError("llm strategy requires a proposal_client")

    risk_engine, breaker, _kill = build_risk_stack(halt_flag)
    tracker = PortfolioTracker(
        starting_usdt, universe_symbol, "crypto", spread_bps=costs.spread_bps
    )
    instrument = make_spot_instrument(universe_symbol, costs)
    bar_type = _bar_type(universe_symbol, timeframe)

    config = BacktestEngineConfig(
        trader_id=TraderId("BACKTESTER-001"),
        logging=LoggingConfig(log_level=log_level),
    )
    engine = BacktestEngine(config=config)
    engine.add_venue(
        venue=NAUTILUS_VENUE,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        starting_balances=[Money(float(starting_usdt), USD)],
        base_currency=None,
        fill_model=build_fill_model(costs),
        fee_model=build_fee_model(),
        bar_execution=True,
        trade_execution=False,
    )
    engine.add_instrument(instrument)

    quotes_df = _quotes_frame(bars, costs.spread_bps)
    bars_df = _bars_frame(bars)
    quotes = QuoteTickDataWrangler(instrument).process(quotes_df)
    nautilus_bars = BarDataWrangler(bar_type, instrument).process(bars_df)
    engine.add_data(quotes)
    engine.add_data(nautilus_bars)

    trade_ns = _trade_start_ns(bars, trade_start)
    if strategy_kind == "baseline":
        strat_config = BaselineEMACrossConfig(
            instrument_id=instrument.id,
            bar_type=bar_type,
            universe_symbol=universe_symbol,
            fast_ema_period=fast_ema_period,
            slow_ema_period=slow_ema_period,
            trade_start_ns=trade_ns,
        )
        strategy = BaselineEMACross(
            strat_config,
            risk_engine=risk_engine,
            circuit_breaker=breaker,
            tracker=tracker,
        )
        strategy.set_source_bars(bars)
    elif strategy_kind in GENERIC_SPEC_KINDS:
        raw_params = strategy_params if strategy_params is not None else default_params_for_kind(
            strategy_kind
        )
        strat_config_generic = GenericSignalStrategyConfig(
            instrument_id=instrument.id,
            bar_type=bar_type,
            universe_symbol=universe_symbol,
            strategy_kind=strategy_kind,
            params={key: str(value) for key, value in raw_params.items()},
            trade_start_ns=trade_ns,
        )
        strategy = GenericSignalStrategy(
            strat_config_generic,
            risk_engine=risk_engine,
            circuit_breaker=breaker,
            tracker=tracker,
        )
        strategy.set_source_bars(bars)
    else:
        strat_config_llm = LLMAssistedStrategyConfig(
            instrument_id=instrument.id,
            bar_type=bar_type,
            universe_symbol=universe_symbol,
            fast_ema_period=fast_ema_period,
            slow_ema_period=slow_ema_period,
            lookback_bars=lookback_bars,
            trade_start_ns=trade_ns,
        )
        strategy = LLMAssistedStrategy(
            strat_config_llm,
            risk_engine=risk_engine,
            circuit_breaker=breaker,
            tracker=tracker,
            proposal_client=proposal_client,
            research_client=research_client,
        )
        strategy.set_source_bars(bars)
    engine.add_strategy(strategy)
    engine.run()

    fills = engine.trader.generate_order_fills_report()
    account = engine.trader.generate_account_report(NAUTILUS_VENUE)
    n_fills = 0 if fills is None or fills.empty else len(fills)
    commissions = Decimal("0")
    if fills is not None and not fills.empty and "commissions" in fills.columns:
        commissions = sum((_parse_money_cell(v) for v in fills["commissions"]), Decimal("0"))
    ending = _ending_usdt(account, starting_usdt)
    decisions = list(getattr(strategy, "decisions", []))
    engine.dispose()

    extra = _build_extra_metrics(
        bars=bars,
        tracker=tracker,
        starting_usdt=starting_usdt,
        timeframe=timeframe,
        spread_bps=costs.spread_bps,
        n_fills=int(n_fills),
    )

    return BacktestMetrics(
        strategy=strategy_kind,
        cost_multiplier=costs.cost_multiplier,
        dataset_hash=dataset_hash,
        n_bars=len(bars),
        n_fills=int(n_fills),
        n_decisions=len(decisions),
        ending_usdt=format(ending, "f"),
        commissions_usdt=format(commissions, "f"),
        decisions=decisions,
        extra=extra,
    )


def _build_extra_metrics(
    *,
    bars: list[Bar],
    tracker: PortfolioTracker,
    starting_usdt: Decimal,
    timeframe: str,
    spread_bps: Decimal,
    n_fills: int,
) -> dict[str, Any]:
    """Metrici complete + baseline-uri + regime slices. Izolat într-o funcție separată ca
    să poată fi testat/reutilizat fără a rula din nou întregul motor Nautilus."""
    performance = backtest_metrics.compute_performance_metrics(
        tracker.equity_curve,
        tracker.closed_trades,
        total_fees=tracker.total_fees,
        total_turnover=tracker.total_turnover,
        starting_cash=starting_usdt,
        timeframe=timeframe,
        spread_bps=spread_bps,
    )

    buy_hold_pct = baselines.buy_and_hold_return_pct(bars)
    trade_rate = (n_fills / len(bars)) if bars else 0.0
    random_pct = (
        baselines.random_control_return_pct(bars, trade_rate=trade_rate)
        if trade_rate > 0
        else None
    )

    tags = regime_mod.tag_regimes(bars)
    regime_breakdown = {
        dimension: backtest_metrics.slice_by_regime(
            tracker.equity_curve, tags, dimension=dimension
        )
        for dimension in REGIME_DIMENSIONS
    }

    equity_curve = [
        {"t": ts.isoformat(), "equity": format(eq, "f"), "exposure": format(exp, "f")}
        for ts, eq, exp in tracker.equity_curve
    ]
    peak = None
    drawdown_curve: list[dict[str, str]] = []
    for ts, eq, _exp in tracker.equity_curve:
        peak = eq if peak is None or eq > peak else peak
        dd_pct = ((peak - eq) / peak * Decimal("100")) if peak and peak > 0 else Decimal("0")
        drawdown_curve.append({"t": ts.isoformat(), "drawdown_pct": format(dd_pct, "f")})
    buy_hold_curve = [
        {"t": ts.isoformat(), "equity": format(eq, "f")}
        for ts, eq in baselines.buy_and_hold_equity_curve(bars, starting_usdt)
    ]

    return {
        "performance": performance.to_dict(),
        "baselines": {
            "buy_and_hold_pct": format(buy_hold_pct, "f") if buy_hold_pct is not None else None,
            "cash_pct": format(baselines.cash_return_pct(), "f"),
            "random_control_pct": (
                format(random_pct, "f") if random_pct is not None else None
            ),
        },
        "regime": regime_breakdown,
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "buy_and_hold_curve": buy_hold_curve,
        "trade_pnls": [format(t, "f") for t in tracker.closed_trades],
        # Structured round-trip trades (design §8.6 `backtest_trades`) — same order
        # as `trade_pnls` above, serialized (not live Decimal/datetime) so this dict
        # stays a plain JSON-able payload like the rest of `extra`. Consumed by
        # `src/engine/backtest_store.py::insert_trades_from_extra` when
        # BACKTEST_STORE_BACKEND=postgres; ignored by the files-only path.
        "closed_trade_records": [
            {
                "side": t.side,
                "entry_time": t.entry_time.isoformat(),
                "entry_price": format(t.entry_price, "f"),
                "exit_time": t.exit_time.isoformat(),
                "exit_price": format(t.exit_price, "f"),
                "quantity": format(t.quantity, "f"),
                "pnl": format(t.pnl, "f"),
                "fees": format(t.fees, "f"),
                "exit_reason": t.exit_reason,
            }
            for t in tracker.closed_trade_records
        ],
    }


def _parse_money_cell(value: object) -> Decimal:
    found = re.findall(r"\d+\.\d+", str(value))
    return sum((Decimal(item) for item in found), Decimal("0"))


def _ending_usdt(account: pd.DataFrame, fallback: Decimal) -> Decimal:
    if account is None or account.empty:
        return fallback
    if "currency" in account.columns and "total" in account.columns:
        usdt = account[account["currency"].astype(str).str.upper().isin({"USD", "USDT"})]
        if not usdt.empty:
            return Decimal(str(usdt.iloc[-1]["total"]))
    return fallback


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
