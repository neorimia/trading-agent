"""RiskEngine — singura cale de la ParsedProposal la o decizie de mărime.

Primește ParsedProposal din engine/, niciodată un tip din llm/.
Limitele vin exclusiv din RiskLimits (config), nu din câmpurile propunerii.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.engine.proposal_types import ParsedProposal
from src.risk.config_schema import RiskLimits
from src.risk.kill_switch import KillSwitch
from src.risk.portfolio_state import InstrumentRules, PortfolioState
from src.risk.position_sizing import size_position

_STRICT = ConfigDict(extra="forbid")

Side = Literal["buy", "sell"]

# Stop intern conservator (2% din preț). Nu e citit din LLM — ParsedProposal
# nu are câmp de stop; distanța e un parametru de risc al motorului.
_DEFAULT_STOP_FRACTION = Decimal("0.02")
_DEFAULT_COST_ESTIMATE = Decimal("0")
_DEFAULT_SLIPPAGE_BUFFER = Decimal("0")


class RiskDecision(BaseModel):
    """Ieșirea evaluate(). `side` e convențional 'buy' când approved=False (câmp fără sens)."""

    model_config = _STRICT

    approved: bool
    instrument: str = Field(min_length=1)
    side: Side
    quantity: Decimal
    reject_reason: str | None
    requires_human_approval: bool


class RiskEngine:
    def __init__(
        self,
        limits: RiskLimits,
        instrument_rules: dict[str, InstrumentRules],
        asset_class_by_instrument: dict[str, str],
        kill_switch: KillSwitch,
    ) -> None:
        self._limits = limits
        self._instrument_rules = instrument_rules
        self._asset_class_by_instrument = asset_class_by_instrument
        self._kill_switch = kill_switch

    def evaluate(self, proposal: ParsedProposal, portfolio_state: PortfolioState) -> RiskDecision:
        instrument = proposal.instrument
        if self._kill_switch.is_active():
            return self._reject(instrument, "halted")
        rules = self._instrument_rules.get(instrument)
        if rules is None:
            return self._reject(instrument, "instrument_not_in_universe")
        if proposal.direction == "avoid":
            return self._reject(instrument, "no_action_proposed")
        if portfolio_state.orders_today >= self._limits.max_orders_per_day:
            return self._reject(instrument, "max_orders_per_day")
        if portfolio_state.daily_realized_loss >= self._limits.max_daily_loss:
            return self._reject(instrument, "max_daily_loss")
        if portfolio_state.current_drawdown >= self._limits.max_drawdown:
            return self._reject(instrument, "max_drawdown")

        if proposal.direction == "exit":
            return self._evaluate_exit(instrument, portfolio_state)

        return self._evaluate_long(instrument, rules, portfolio_state)

    def _evaluate_exit(
        self, instrument: str, portfolio_state: PortfolioState
    ) -> RiskDecision:
        open_qty = portfolio_state.open_quantity.get(instrument, Decimal("0"))
        if open_qty <= 0:
            return self._reject(instrument, "no_open_position")
        return RiskDecision(
            approved=True,
            instrument=instrument,
            side="sell",
            quantity=open_qty,
            reject_reason=None,
            requires_human_approval=True,
        )

    def _evaluate_long(
        self,
        instrument: str,
        rules: InstrumentRules,
        portfolio_state: PortfolioState,
    ) -> RiskDecision:
        price = portfolio_state.last_price.get(instrument)
        if price is None or price <= 0:
            return self._reject(instrument, "missing_price")

        asset_class = self._asset_class_by_instrument.get(instrument)
        if asset_class is None:
            return self._reject(instrument, "instrument_not_in_universe")

        current_instrument = portfolio_state.exposure_per_instrument.get(instrument, Decimal("0"))
        current_class = portfolio_state.exposure_per_asset_class.get(asset_class, Decimal("0"))
        remaining_instrument = self._limits.max_exposure_per_instrument - current_instrument
        remaining_class = self._limits.max_exposure_per_asset_class - current_class
        cap_notional = min(
            self._limits.max_notional_per_order,
            remaining_instrument,
            remaining_class,
        )
        remaining_daily = self._limits.max_daily_loss - portfolio_state.daily_realized_loss
        remaining_drawdown = self._limits.max_drawdown - portfolio_state.current_drawdown
        risk_budget = min(remaining_daily, remaining_drawdown)
        if cap_notional <= 0 or risk_budget <= 0:
            return self._reject(instrument, "below_min_notional_or_no_capacity")

        stop_distance = price * _DEFAULT_STOP_FRACTION
        quantity = size_position(
            cap_notional=cap_notional,
            price=price,
            risk_budget=risk_budget,
            stop_distance=stop_distance,
            cost_estimate=_DEFAULT_COST_ESTIMATE,
            slippage_buffer=_DEFAULT_SLIPPAGE_BUFFER,
            instrument_rules=rules,
        )
        if quantity <= 0:
            return self._reject(instrument, "below_min_notional_or_no_capacity")

        return RiskDecision(
            approved=True,
            instrument=instrument,
            side="buy",
            quantity=quantity,
            reject_reason=None,
            requires_human_approval=True,
        )

    @staticmethod
    def _reject(instrument: str, reason: str) -> RiskDecision:
        return RiskDecision(
            approved=False,
            instrument=instrument,
            side="buy",
            quantity=Decimal("0"),
            reject_reason=reason,
            requires_human_approval=True,
        )
