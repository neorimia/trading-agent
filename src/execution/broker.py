"""BrokerClient protocol + SimulatedBroker (dry_run local, zero chei de exchange)."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.engine.cost_models import BASE_TAKER_FEE
from src.execution.types import OrderRequest, OrderResult

_STRICT = ConfigDict(extra="forbid")

SimulatedOutcome = Literal[
    "filled",
    "partially_filled",
    "rejected",
    "unknown",
    "timeout",
]


class BrokerState(BaseModel):
    """Snapshot de poziții + ordine deschise, pentru reconciliere."""

    model_config = _STRICT

    positions: dict[str, Decimal] = Field(default_factory=dict)
    open_client_order_ids: list[str] = Field(default_factory=list)
    last_price: dict[str, Decimal] = Field(default_factory=dict)


class BrokerClient(Protocol):
    def submit(self, order: OrderRequest) -> OrderResult: ...

    def cancel_all(self, reason: str) -> None: ...

    def snapshot(self) -> BrokerState: ...


class SimulatedBroker:
    """Execuție locală dry_run. Fill-uri simulate la last_price; fără rețea."""

    def __init__(
        self,
        *,
        default_outcome: SimulatedOutcome = "filled",
        partial_fraction: Decimal = Decimal("0.4"),
    ) -> None:
        if partial_fraction <= 0 or partial_fraction >= 1:
            raise ValueError("partial_fraction must be in (0, 1)")
        self._default_outcome = default_outcome
        self._partial_fraction = partial_fraction
        self._outcomes: dict[str, SimulatedOutcome] = {}
        self._positions: dict[str, Decimal] = {}
        self._open: dict[str, OrderRequest] = {}
        self._last_price: dict[str, Decimal] = {}
        self._cancelled = False

    def set_last_price(self, instrument: str, price: Decimal) -> None:
        if price <= 0:
            raise ValueError("price must be positive")
        self._last_price[instrument] = price

    def set_outcome(self, client_order_id: str, outcome: SimulatedOutcome) -> None:
        self._outcomes[client_order_id] = outcome

    def submit(self, order: OrderRequest) -> OrderResult:
        key = str(order.client_order_id)
        outcome = self._outcomes.get(key, self._default_outcome)
        broker_id = f"sim-{uuid4()}"
        if outcome == "rejected":
            return OrderResult(
                client_order_id=order.client_order_id,
                status="rejected",
                broker_order_id=None,
                reason="simulated_reject",
            )
        if outcome == "timeout":
            self._open[key] = order
            return OrderResult(
                client_order_id=order.client_order_id,
                status="timeout",
                broker_order_id=None,
                reason="simulated_timeout",
            )
        if outcome == "unknown":
            self._open[key] = order
            return OrderResult(
                client_order_id=order.client_order_id,
                status="unknown",
                broker_order_id=broker_id,
                reason="simulated_unknown",
            )
        price = self._last_price.get(order.instrument)
        if price is None:
            return OrderResult(
                client_order_id=order.client_order_id,
                status="rejected",
                reason="missing_price",
            )
        filled_qty = order.quantity
        status: Literal["filled", "partially_filled"] = "filled"
        if outcome == "partially_filled":
            filled_qty = (order.quantity * self._partial_fraction).quantize(
                Decimal("0.00000001")
            )
            if filled_qty <= 0:
                filled_qty = order.quantity
            status = "partially_filled"
            remaining = order.quantity - filled_qty
            if remaining > 0:
                self._open[key] = order
        self._apply_fill(order, filled_qty)
        # Aproximare taker-only (paper nu distinge maker/taker ca Nautilus în backtest) —
        # fără asta paper era artificial de optimist (comision 0 la fiecare fill).
        fee = (filled_qty * price * BASE_TAKER_FEE).quantize(Decimal("0.00000001"))
        return OrderResult(
            client_order_id=order.client_order_id,
            status=status,
            broker_order_id=broker_id,
            filled_quantity=filled_qty,
            fill_price=price,
            fee=fee,
        )

    def cancel_all(self, reason: str) -> None:
        if not reason.strip():
            raise ValueError("cancel_all reason must be a non-empty string")
        self._open.clear()
        self._cancelled = True

    def snapshot(self) -> BrokerState:
        return BrokerState(
            positions=dict(self._positions),
            open_client_order_ids=sorted(self._open.keys()),
            last_price=dict(self._last_price),
        )

    def restore(self, state: BrokerState) -> None:
        """Reconstituire după restart — doar stare, fără resubmit."""
        self._positions = dict(state.positions)
        self._last_price = dict(state.last_price)
        self._open = {}
        self._cancelled = False

    def _apply_fill(self, order: OrderRequest, quantity: Decimal) -> None:
        current = self._positions.get(order.instrument, Decimal("0"))
        if order.side == "buy":
            self._positions[order.instrument] = current + quantity
            return
        closed = min(current, quantity)
        self._positions[order.instrument] = current - closed
