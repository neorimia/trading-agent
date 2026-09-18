"""Costuri de venue: comision maker/taker, spread bid/ask, slippage + fills parțiale.

Multiplicatorul 1×/2×/3× scalează comisionul, spread-ul și tick-urile de slippage.
Fill-ul e determinist (seed fix, fără RNG la 1.0/0.0 probabilities pe limit).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from nautilus_trader.backtest.models.fee import MakerTakerFeeModel
from nautilus_trader.backtest.models.fill import FillModel
from nautilus_trader.model.book import OrderBook
from nautilus_trader.model.data import BookOrder
from nautilus_trader.model.enums import BookType, OrderSide
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.orders import Order

# Spot crypto tipic fără discount BNB: 10 bps taker. Spread conservator 10 bps.
BASE_MAKER_FEE = Decimal("0.001")
BASE_TAKER_FEE = Decimal("0.001")
BASE_SPREAD_BPS = Decimal("10")
FILL_RANDOM_SEED = 42
TOP_OF_BOOK_FRACTION = 0.4


@dataclass(frozen=True)
class VenueCostConfig:
    cost_multiplier: int
    maker_fee: Decimal
    taker_fee: Decimal
    spread_bps: Decimal
    slippage_ticks: int
    random_seed: int = FILL_RANDOM_SEED

    @classmethod
    def for_multiplier(cls, multiplier: int, *, random_seed: int = FILL_RANDOM_SEED) -> VenueCostConfig:
        if multiplier not in {1, 2, 3}:
            raise ValueError("cost_multiplier must be 1, 2, or 3")
        scale = Decimal(multiplier)
        return cls(
            cost_multiplier=multiplier,
            maker_fee=BASE_MAKER_FEE * scale,
            taker_fee=BASE_TAKER_FEE * scale,
            spread_bps=BASE_SPREAD_BPS * scale,
            slippage_ticks=multiplier,
            random_seed=random_seed,
        )


class PartialSlippageFillModel(FillModel):
    """40% din cantitate la best bid/ask, restul la N tick-uri mai rău (N = cost_multiplier).

    Determinist: nu folosește probabilități în (0, 1). Modelează simultan
    slippage-ul și fill-urile parțiale cerute de Task 4.
    """

    def __init__(self, slippage_ticks: int, random_seed: int = FILL_RANDOM_SEED) -> None:
        if slippage_ticks < 1:
            raise ValueError("slippage_ticks must be >= 1")
        super().__init__(prob_fill_on_limit=1.0, prob_slippage=0.0, random_seed=random_seed)
        self._slippage_ticks = slippage_ticks

    def get_orderbook_for_fill_simulation(
        self,
        instrument: Instrument,
        order: Order,
        best_bid: Price,
        best_ask: Price,
    ) -> OrderBook:
        book = OrderBook(instrument_id=instrument.id, book_type=BookType.L2_MBP)
        order_qty = float(order.quantity)
        top_qty = max(float(instrument.size_increment), order_qty * TOP_OF_BOOK_FRACTION)
        rest_qty = 1_000_000.0
        tick = instrument.price_increment
        tick_val = tick.as_double() * self._slippage_ticks
        slipped_bid = Price(best_bid.as_double() - tick_val, precision=best_bid.precision)
        slipped_ask = Price(best_ask.as_double() + tick_val, precision=best_ask.precision)
        size_precision = instrument.size_precision
        book.add(
            BookOrder(
                side=OrderSide.BUY,
                price=best_bid,
                size=Quantity(top_qty, size_precision),
                order_id=1,
            ),
            0,
            0,
        )
        book.add(
            BookOrder(
                side=OrderSide.SELL,
                price=best_ask,
                size=Quantity(top_qty, size_precision),
                order_id=2,
            ),
            0,
            0,
        )
        book.add(
            BookOrder(
                side=OrderSide.BUY,
                price=slipped_bid,
                size=Quantity(rest_qty, size_precision),
                order_id=3,
            ),
            0,
            0,
        )
        book.add(
            BookOrder(
                side=OrderSide.SELL,
                price=slipped_ask,
                size=Quantity(rest_qty, size_precision),
                order_id=4,
            ),
            0,
            0,
        )
        return book


def build_fee_model() -> MakerTakerFeeModel:
    return MakerTakerFeeModel()


def build_fill_model(config: VenueCostConfig) -> PartialSlippageFillModel:
    return PartialSlippageFillModel(config.slippage_ticks, random_seed=config.random_seed)
