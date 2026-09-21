"""Adaptor Nautilus generic peste orice `StrategySpec` — semnal -> RiskEngine -> ordin.

Un singur `Strategy` Nautilus pentru toate strategiile rule-based (`ema_cross`,
`donchian_breakout`, `rsi_mean_reversion`), înlocuind nevoia de a scrie o clasă Nautilus
nouă per strategie. `HOLD` nu ajunge niciodată la RiskEngine. Cooldown și "max poziții
simultane" sunt aplicate AICI, înainte de RiskEngine — o strategie poate doar restrânge
comportamentul (skip local), niciodată nu poate lărgi limitele globale de risc.

Kind-ul `llm` nu trece prin acest adaptor — rulează prin
`src/engine/strategy_llm_assisted.py`, neschimbat (are nevoie de un `ProposalClient`,
nu se încadrează în `StrategySpec.evaluate(bars) -> signal` pur).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.datetime import unix_nanos_to_dt
from nautilus_trader.model.data import Bar as NautilusBar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.strategy import Strategy

from src.data.sources import Bar
from src.engine.portfolio_tracker import PortfolioTracker
from src.engine.proposal_types import ParsedProposal
from src.engine.strategy_registry import build_spec_from_kind_and_params
from src.engine.strategy_spec import StrategySpec, reward_risk_ratio
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.risk_engine import RiskEngine

# Cât timp nu s-a văzut niciun exit, cooldown-ul nu blochează nimic.
_NEVER_EXITED = 10**9


class GenericSignalStrategyConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    universe_symbol: str
    strategy_kind: str
    params: dict[str, str] = {}
    trade_start_ns: int = 0


class GenericSignalStrategy(Strategy):
    """Strategia NU decide cantitatea și nu trimite ordinul dacă RiskEngine respinge."""

    def __init__(
        self,
        config: GenericSignalStrategyConfig,
        *,
        risk_engine: RiskEngine,
        circuit_breaker: CircuitBreaker,
        tracker: PortfolioTracker,
    ) -> None:
        super().__init__(config)
        self._risk_engine = risk_engine
        self._circuit_breaker = circuit_breaker
        self._tracker = tracker
        self._spec: StrategySpec = build_spec_from_kind_and_params(
            config.strategy_kind, dict(config.params), id=config.strategy_kind
        )
        self._source_bars: list[Bar] = []
        self._bar_index = 0
        self._history: list[Bar] = []
        self._bars_since_exit = _NEVER_EXITED
        self.decisions: list[str] = []
        self.signals: list[str] = []

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
        if len(self._history) < self._spec.warmup_bars():
            return

        signal = self._spec.evaluate(self._history)
        self.signals.append(
            f"{our_bar.timestamp.isoformat()}|{signal.side}|{signal.confidence:.3f}|{signal.reason}"
        )
        if signal.side == "hold":
            self._bars_since_exit += 1
            return

        if signal.side == "buy":
            if self._bars_since_exit < self._spec.cooldown_bars:
                self.decisions.append(
                    f"{our_bar.timestamp.isoformat()}|cooldown_skip|{self._bars_since_exit}<{self._spec.cooldown_bars}"
                )
                self._bars_since_exit += 1
                return
            if not self.portfolio.is_flat(self.config.instrument_id):
                # max_simultaneous_positions=1, structural pentru un singur instrument.
                self._bars_since_exit += 1
                return
            direction = "long"
        else:
            direction = "exit"

        proposal = ParsedProposal(
            instrument=our_bar.instrument,
            direction=direction,
            confidence=signal.confidence,
            rationale=signal.reason,
        )
        state = self._tracker.snapshot(our_bar.close)
        rr = reward_risk_ratio(our_bar.close, signal.stop_price, signal.take_profit_price)
        decision = self._risk_engine.evaluate(proposal, state, reward_risk_ratio=rr)
        self.decisions.append(
            f"{our_bar.timestamp.isoformat()}|{direction}|{decision.approved}|{decision.quantity}|{decision.reject_reason}"
        )
        self._bars_since_exit += 1
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
        commission = (
            Decimal(str(event.commission.as_double())) if event.commission is not None else Decimal("0")
        )
        side = "buy" if event.order_side == OrderSide.BUY else "sell"
        self._tracker.on_fill(
            side=side,
            quantity=Decimal(str(event.last_qty)),
            price=Decimal(str(event.last_px)),
            commission=commission,
        )
        if side == "sell":
            self._bars_since_exit = 0
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
