"""Strategie baseline EMA-cross, long-only, fără LLM — trece prin RiskEngine."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from nautilus_trader.config import PositiveInt, StrategyConfig
from nautilus_trader.core.datetime import unix_nanos_to_dt
from nautilus_trader.model.data import Bar as NautilusBar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.strategy import Strategy

from src.data.sources import Bar
from src.engine.portfolio_tracker import PortfolioTracker
from src.engine.signals import baseline_proposal
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.risk_engine import RiskEngine


class BaselineEMACrossConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    universe_symbol: str
    fast_ema_period: PositiveInt = 10
    slow_ema_period: PositiveInt = 20
    trade_start_ns: int = 0


class BaselineEMACross(Strategy):
    """EMA-cross determinist. Mărimea poziției vine exclusiv din RiskEngine."""

    def __init__(
        self,
        config: BaselineEMACrossConfig,
        *,
        risk_engine: RiskEngine,
        circuit_breaker: CircuitBreaker,
        tracker: PortfolioTracker,
    ) -> None:
        super().__init__(config)
        self._risk_engine = risk_engine
        self._circuit_breaker = circuit_breaker
        self._tracker = tracker
        self._source_bars: list[Bar] = []
        self._bar_index = 0
        self._history: list[Bar] = []
        self.decisions: list[str] = []

    def set_source_bars(self, bars: list[Bar]) -> None:
        self._source_bars = bars
        self._bar_index = 0

    def on_start(self) -> None:
        instrument = self.cache.instrument(self.config.instrument_id)
        if instrument is None:
            self.stop()
            return
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar: NautilusBar) -> None:
        if self._bar_index >= len(self._source_bars):
            our_bar = _from_nautilus(self.config.universe_symbol, bar)
        else:
            our_bar = self._source_bars[self._bar_index]
            self._bar_index += 1
        if our_bar.timestamp < _from_ns(self.config.trade_start_ns) and self.config.trade_start_ns:
            self._history.append(our_bar)
            self._tracker.on_bar(our_bar.timestamp, our_bar.close, volume=our_bar.volume)
            return
        self._history.append(our_bar)
        self._tracker.on_bar(our_bar.timestamp, our_bar.close, volume=our_bar.volume)
        proposal = baseline_proposal(
            self._history,
            fast_period=int(self.config.fast_ema_period),
            slow_period=int(self.config.slow_ema_period),
        )
        if proposal is None:
            return
        state = self._tracker.snapshot(our_bar.close)
        decision = self._risk_engine.evaluate(proposal, state)
        self.decisions.append(f"{our_bar.timestamp.isoformat()}|{proposal.direction}|{decision.approved}|{decision.quantity}")
        if not decision.approved or decision.quantity <= 0:
            return
        if self._circuit_breaker.state == "HALTED":
            return
        instrument = self.cache.instrument(self.config.instrument_id)
        if instrument is None:
            return
        if decision.side == "buy" and not self.portfolio.is_flat(self.config.instrument_id):
            return
        if decision.side == "sell" and self.portfolio.is_flat(self.config.instrument_id):
            return
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.BUY if decision.side == "buy" else OrderSide.SELL,
            quantity=instrument.make_qty(decision.quantity),
            time_in_force=TimeInForce.GTC,
        )
        self._tracker.record_order_submit()
        self.submit_order(order)

    def on_event(self, event) -> None:  # noqa: ANN001 — Nautilus Event
        if not isinstance(event, OrderFilled):
            return
        commission = Decimal(str(event.commission.as_double())) if event.commission is not None else Decimal("0")
        side = "buy" if event.order_side == OrderSide.BUY else "sell"
        self._tracker.on_fill(
            side=side,
            quantity=Decimal(str(event.last_qty)),
            price=Decimal(str(event.last_px)),
            commission=commission,
            timestamp=unix_nanos_to_dt(event.ts_event).replace(tzinfo=timezone.utc),
        )
        if event.is_buy:
            self._circuit_breaker.record_event("success")
        else:
            snapshot = self._tracker.snapshot(Decimal(str(event.last_px)))
            if snapshot.daily_realized_loss > 0:
                self._circuit_breaker.record_event("loss")
            else:
                self._circuit_breaker.record_event("success")


def _from_ns(ts_ns: int) -> datetime:
    if ts_ns <= 0:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    return unix_nanos_to_dt(ts_ns).replace(tzinfo=timezone.utc)


def _from_nautilus(instrument: str, bar: NautilusBar) -> Bar:
    ts = unix_nanos_to_dt(bar.ts_event)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)
    return Bar(
        instrument=instrument,
        timestamp=ts,
        open=Decimal(str(bar.open)),
        high=Decimal(str(bar.high)),
        low=Decimal(str(bar.low)),
        close=Decimal(str(bar.close)),
        volume=Decimal(str(bar.volume)),
    )
