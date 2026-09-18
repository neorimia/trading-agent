"""Tracker de portofoliu determinist — input pentru RiskEngine în timpul backtestului."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from src.risk.portfolio_state import PortfolioState


class PortfolioTracker:
    def __init__(self, starting_cash: Decimal, instrument: str, asset_class: str) -> None:
        if starting_cash <= 0:
            raise ValueError("starting_cash must be positive")
        self._starting_cash = starting_cash
        self._cash = starting_cash
        self._instrument = instrument
        self._asset_class = asset_class
        self._open_qty = Decimal("0")
        self._avg_price = Decimal("0")
        self._realized_pnl_today = Decimal("0")
        self._day_key: str | None = None
        self._orders_today = 0
        self._peak_equity = starting_cash

    def on_bar(self, timestamp: datetime, last_price: Decimal) -> None:
        day_key = timestamp.date().isoformat()
        if self._day_key != day_key:
            self._day_key = day_key
            self._realized_pnl_today = Decimal("0")
            self._orders_today = 0
        equity = self._equity(last_price)
        if equity > self._peak_equity:
            self._peak_equity = equity

    def record_order_submit(self) -> None:
        self._orders_today += 1

    def on_fill(
        self,
        *,
        side: str,
        quantity: Decimal,
        price: Decimal,
        commission: Decimal,
    ) -> None:
        qty = quantity
        if qty <= 0:
            return
        self._cash -= commission
        if side == "buy":
            cost = qty * price
            self._cash -= cost
            new_qty = self._open_qty + qty
            if new_qty > 0:
                self._avg_price = (
                    (self._avg_price * self._open_qty) + cost
                ) / new_qty
            self._open_qty = new_qty
            return
        # sell — reduce long (long-only)
        closed = min(self._open_qty, qty)
        proceeds = qty * price
        self._cash += proceeds
        if closed > 0 and self._avg_price > 0:
            self._realized_pnl_today += (price - self._avg_price) * closed
            self._open_qty -= closed
            if self._open_qty == 0:
                self._avg_price = Decimal("0")

    def snapshot(self, last_price: Decimal) -> PortfolioState:
        exposure = abs(self._open_qty * last_price)
        equity = self._equity(last_price)
        drawdown = self._peak_equity - equity
        if drawdown < 0:
            drawdown = Decimal("0")
        daily_loss = -self._realized_pnl_today if self._realized_pnl_today < 0 else Decimal("0")
        return PortfolioState(
            exposure_per_instrument={self._instrument: exposure},
            exposure_per_asset_class={self._asset_class: exposure},
            daily_realized_loss=daily_loss,
            current_drawdown=drawdown,
            orders_today=self._orders_today,
            last_price={self._instrument: last_price},
            open_quantity={self._instrument: self._open_qty},
        )

    def _equity(self, last_price: Decimal) -> Decimal:
        return self._cash + (self._open_qty * last_price)
