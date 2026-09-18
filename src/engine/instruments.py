"""Instrumente spot crypto pentru backtestul NautilusTrader (venue simulat BINANCE).

Simbolul din universe.yaml (ETHUSD/BTCUSD) rămâne identitatea de risc/LLM;
Nautilus folosește ETHUSDT.BINANCE / BTCUSDT.BINANCE pentru date + matching.
"""

from __future__ import annotations

from decimal import Decimal

from nautilus_trader.model.currencies import BTC, ETH, USDT
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Money, Price, Quantity

from src.engine.cost_models import VenueCostConfig

NAUTILUS_VENUE = Venue("BINANCE")

_UNIVERSE_TO_NAUTILUS = {
    "ETHUSD": ("ETHUSDT", ETH, 2, 5, Decimal("0.01"), Decimal("0.00001")),
    "BTCUSD": ("BTCUSDT", BTC, 2, 6, Decimal("0.01"), Decimal("0.000001")),
}


def nautilus_symbol(universe_symbol: str) -> str:
    spec = _UNIVERSE_TO_NAUTILUS.get(universe_symbol)
    if spec is None:
        raise ValueError(f"no nautilus mapping for {universe_symbol!r}")
    return spec[0]


def make_spot_instrument(universe_symbol: str, costs: VenueCostConfig) -> CurrencyPair:
    spec = _UNIVERSE_TO_NAUTILUS.get(universe_symbol)
    if spec is None:
        raise ValueError(f"no nautilus mapping for {universe_symbol!r}")
    raw, base, price_precision, size_precision, price_inc, size_inc = spec
    return CurrencyPair(
        instrument_id=InstrumentId(symbol=Symbol(raw), venue=NAUTILUS_VENUE),
        raw_symbol=Symbol(raw),
        base_currency=base,
        quote_currency=USDT,
        price_precision=price_precision,
        size_precision=size_precision,
        price_increment=Price(price_inc, precision=price_precision),
        size_increment=Quantity(size_inc, precision=size_precision),
        lot_size=None,
        max_quantity=Quantity(9000, precision=size_precision),
        min_quantity=Quantity(size_inc, precision=size_precision),
        max_notional=None,
        min_notional=Money(10.00, USDT),
        max_price=Price(1_000_000, precision=price_precision),
        min_price=Price(price_inc, precision=price_precision),
        margin_init=Decimal("0"),
        margin_maint=Decimal("0"),
        maker_fee=costs.maker_fee,
        taker_fee=costs.taker_fee,
        ts_event=0,
        ts_init=0,
    )
