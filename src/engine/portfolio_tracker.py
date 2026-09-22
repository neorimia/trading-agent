"""Tracker de portofoliu determinist — input pentru RiskEngine în timpul backtestului."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from src.risk.portfolio_state import PortfolioState


@dataclass(frozen=True)
class ClosedTrade:
    """Round-trip long-only entry->exit — the structured shape `backtest_trades`
    (docs/database-design.md §8.6) needs, in parallel with the legacy PnL-only
    `closed_trades` list (kept for `src/engine/metrics.py` compatibility).

    `entry_time`/`entry_price` are the position's weighted-average entry (set on
    the fill that opened the position from flat; unchanged by later same-direction
    adds). `fees` is only the closing fill's commission — opening-fill commissions
    already reduced cash but are not attributable to one specific closed lot once
    multiple buys have blended into a single average price (documented
    simplification, not a fabricated split)."""

    side: str
    entry_time: datetime
    entry_price: Decimal
    exit_time: datetime
    exit_price: Decimal
    quantity: Decimal
    pnl: Decimal
    fees: Decimal
    exit_reason: str | None = None


class PortfolioTracker:
    def __init__(
        self,
        starting_cash: Decimal,
        instrument: str,
        asset_class: str,
        *,
        spread_bps: Decimal | None = None,
    ) -> None:
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
        # Spread constant per rulare (din cost model), folosit de RiskEngine.max_spread_bps.
        self._spread_bps = spread_bps
        self._last_volume: Decimal | None = None
        # Istoric pentru metrici (nu resetat zilnic, spre deosebire de realized_pnl_today).
        # Fiecare punct: (timestamp, equity, exposure_absolută_la_bara_respectivă).
        self._equity_curve: list[tuple[datetime, Decimal, Decimal]] = []
        self._closed_trades: list[Decimal] = []
        self._closed_trade_records: list[ClosedTrade] = []
        self._entry_time: datetime | None = None
        self._total_fees = Decimal("0")
        self._total_turnover = Decimal("0")

    def on_bar(
        self,
        timestamp: datetime,
        last_price: Decimal,
        *,
        volume: Decimal | None = None,
    ) -> None:
        day_key = timestamp.date().isoformat()
        if self._day_key != day_key:
            self._day_key = day_key
            self._realized_pnl_today = Decimal("0")
            self._orders_today = 0
        equity = self._equity(last_price)
        if equity > self._peak_equity:
            self._peak_equity = equity
        if volume is not None:
            self._last_volume = volume
        exposure = abs(self._open_qty * last_price)
        self._equity_curve.append((timestamp, equity, exposure))

    def record_order_submit(self) -> None:
        self._orders_today += 1

    def on_fill(
        self,
        *,
        side: str,
        quantity: Decimal,
        price: Decimal,
        commission: Decimal,
        timestamp: datetime,
        exit_reason: str | None = None,
    ) -> None:
        qty = quantity
        if qty <= 0:
            return
        self._cash -= commission
        self._total_fees += commission
        self._total_turnover += qty * price
        if side == "buy":
            cost = qty * price
            self._cash -= cost
            if self._open_qty == 0:
                self._entry_time = timestamp
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
            trade_pnl = (price - self._avg_price) * closed
            self._realized_pnl_today += trade_pnl
            self._closed_trades.append(trade_pnl)
            entry_time = self._entry_time if self._entry_time is not None else timestamp
            self._closed_trade_records.append(
                ClosedTrade(
                    side="buy",
                    entry_time=entry_time,
                    entry_price=self._avg_price,
                    exit_time=timestamp,
                    exit_price=price,
                    quantity=closed,
                    pnl=trade_pnl,
                    fees=commission,
                    exit_reason=exit_reason,
                )
            )
            self._open_qty -= closed
            if self._open_qty == 0:
                self._avg_price = Decimal("0")
                self._entry_time = None

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
            spread_bps=(
                {self._instrument: self._spread_bps} if self._spread_bps is not None else {}
            ),
            bar_volume=(
                {self._instrument: self._last_volume} if self._last_volume is not None else {}
            ),
        )

    def equity(self, last_price: Decimal) -> Decimal:
        """Cash + valoarea poziției deschise la prețul curent."""
        return self._equity(last_price)

    @property
    def equity_curve(self) -> list[tuple[datetime, Decimal, Decimal]]:
        """Un punct (timestamp, equity, exposure) per bar procesat, în ordine cronologică."""
        return list(self._equity_curve)

    @property
    def closed_trades(self) -> list[Decimal]:
        """P&L brut (înainte de comisioane) per tranzacție închisă (fiecare sell care reduce poziția)."""
        return list(self._closed_trades)

    @property
    def closed_trade_records(self) -> list[ClosedTrade]:
        """Structured round-trip trades (design §8.6 `backtest_trades`), one per
        `closed_trades` entry in the same order — going-forward only, never
        reconstructed from legacy PnL-only history (see `scripts/db/
        import_backtests.py` module docstring)."""
        return list(self._closed_trade_records)

    @property
    def total_fees(self) -> Decimal:
        return self._total_fees

    @property
    def total_turnover(self) -> Decimal:
        """Suma notionalului tranzacționat (buy + sell), folosită pentru turnover."""
        return self._total_turnover

    @property
    def starting_cash(self) -> Decimal:
        return self._starting_cash

    def dump_state(self) -> dict[str, Any]:
        return {
            "starting_cash": str(self._starting_cash),
            "cash": str(self._cash),
            "instrument": self._instrument,
            "asset_class": self._asset_class,
            "open_qty": str(self._open_qty),
            "avg_price": str(self._avg_price),
            "realized_pnl_today": str(self._realized_pnl_today),
            "day_key": self._day_key,
            "orders_today": self._orders_today,
            "peak_equity": str(self._peak_equity),
            "last_volume": str(self._last_volume) if self._last_volume is not None else None,
            "total_fees": str(self._total_fees),
            "total_turnover": str(self._total_turnover),
            "closed_trades": [str(v) for v in self._closed_trades],
            "entry_time": self._entry_time.isoformat() if self._entry_time is not None else None,
            "closed_trade_records": [
                {
                    "side": t.side,
                    "entry_time": t.entry_time.isoformat(),
                    "entry_price": str(t.entry_price),
                    "exit_time": t.exit_time.isoformat(),
                    "exit_price": str(t.exit_price),
                    "quantity": str(t.quantity),
                    "pnl": str(t.pnl),
                    "fees": str(t.fees),
                    "exit_reason": t.exit_reason,
                }
                for t in self._closed_trade_records
            ],
        }

    def restore(self, state: dict[str, Any]) -> None:
        if str(state.get("instrument")) != self._instrument:
            raise ValueError("tracker instrument mismatch on restore")
        self._starting_cash = Decimal(str(state["starting_cash"]))
        self._cash = Decimal(str(state["cash"]))
        self._asset_class = str(state.get("asset_class") or self._asset_class)
        self._open_qty = Decimal(str(state["open_qty"]))
        self._avg_price = Decimal(str(state["avg_price"]))
        self._realized_pnl_today = Decimal(str(state["realized_pnl_today"]))
        day_key = state.get("day_key")
        self._day_key = str(day_key) if day_key else None
        self._orders_today = int(state["orders_today"])
        self._peak_equity = Decimal(str(state["peak_equity"]))
        last_volume = state.get("last_volume")
        self._last_volume = Decimal(str(last_volume)) if last_volume is not None else None
        self._total_fees = Decimal(str(state.get("total_fees", "0")))
        self._total_turnover = Decimal(str(state.get("total_turnover", "0")))
        self._closed_trades = [Decimal(str(v)) for v in state.get("closed_trades", [])]
        entry_time = state.get("entry_time")
        self._entry_time = datetime.fromisoformat(entry_time) if entry_time else None
        self._closed_trade_records = [
            ClosedTrade(
                side=str(record["side"]),
                entry_time=datetime.fromisoformat(record["entry_time"]),
                entry_price=Decimal(str(record["entry_price"])),
                exit_time=datetime.fromisoformat(record["exit_time"]),
                exit_price=Decimal(str(record["exit_price"])),
                quantity=Decimal(str(record["quantity"])),
                pnl=Decimal(str(record["pnl"])),
                fees=Decimal(str(record["fees"])),
                exit_reason=record.get("exit_reason"),
            )
            for record in state.get("closed_trade_records", [])
        ]

    def _equity(self, last_price: Decimal) -> Decimal:
        return self._cash + (self._open_qty * last_price)
