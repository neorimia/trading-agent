"""Strategie LLM-assisted: context -> cache/HTTP -> RiskEngine -> ordin simulat.

Nu importă src.llm. Propunerile respinse nu sunt reparate. Aprobarea umană
(Faza 5) e implicită în backtest: RiskDecision.approved e suficient pentru
submit pe SimulatedVenue.
"""

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
from src.engine.proposal_cache import ProposalClient
from src.engine.proposal_types import ParsedProposal, RejectedProposal
from src.engine.research_client import ResearchClient
from src.engine.signals import proposal_context_at
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.risk_engine import RiskEngine


class LLMAssistedStrategyConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    universe_symbol: str
    fast_ema_period: PositiveInt = 10
    slow_ema_period: PositiveInt = 20
    lookback_bars: PositiveInt = 20
    trade_start_ns: int = 0


class LLMAssistedStrategy(Strategy):
    def __init__(
        self,
        config: LLMAssistedStrategyConfig,
        *,
        risk_engine: RiskEngine,
        circuit_breaker: CircuitBreaker,
        tracker: PortfolioTracker,
        proposal_client: ProposalClient,
        research_client: ResearchClient | None = None,
    ) -> None:
        super().__init__(config)
        self._risk_engine = risk_engine
        self._circuit_breaker = circuit_breaker
        self._tracker = tracker
        self._proposal_client = proposal_client
        self._research_client = research_client
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
        self._history.append(our_bar)
        self._tracker.on_bar(our_bar.timestamp, our_bar.close, volume=our_bar.volume)
        if self.config.trade_start_ns and our_bar.timestamp < _from_ns(self.config.trade_start_ns):
            return
        if len(self._history) < int(self.config.lookback_bars):
            return
        context = proposal_context_at(
            self._history,
            fast_period=int(self.config.fast_ema_period),
            slow_period=int(self.config.slow_ema_period),
            lookback=int(self.config.lookback_bars),
        )
        if self._research_client is not None:
            external_context = self._research_client.get_context(context.instrument, context.as_of)
            if external_context is not None:
                context = context.model_copy(update={"external_context": external_context})
        result = self._proposal_client.request_proposal(context)
        if isinstance(result, RejectedProposal):
            self.decisions.append(f"{our_bar.timestamp.isoformat()}|rejected|{result.reason}")
            return
        if not isinstance(result, ParsedProposal):
            return
        state = self._tracker.snapshot(our_bar.close)
        decision = self._risk_engine.evaluate(result, state)
        self.decisions.append(
            f"{our_bar.timestamp.isoformat()}|{result.direction}|{decision.approved}|{decision.quantity}"
        )
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

    def on_event(self, event) -> None:  # noqa: ANN001
        if not isinstance(event, OrderFilled):
            return
        commission = Decimal(str(event.commission.as_double())) if event.commission is not None else Decimal("0")
        side = "buy" if event.order_side == OrderSide.BUY else "sell"
        self._tracker.on_fill(
            side=side,
            quantity=Decimal(str(event.last_qty)),
            price=Decimal(str(event.last_px)),
            commission=commission,
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
