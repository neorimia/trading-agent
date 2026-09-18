"""Instrumente spot crypto pentru backtestul NautilusTrader (venue simulat KRAKEN).

Simbolul din universe.yaml (ETHUSD/BTCUSD) e identitatea de risc/LLM și de matching.
Istoricul lung poate veni de pe Binance; costurile și venue-ul simulat sunt KRAKEN.
"""

from __future__ import annotations

from decimal import Decimal
from nautilus_trader.model.currencies import BTC, ETH, USD
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Money, Price, Quantity

from src.data.venue_registry import NAUTILUS_VENUE_NAME, get_instrument
from src.engine.cost_models import VenueCostConfig

NAUTILUS_VENUE = Venue(NAUTILUS_VENUE_NAME)

_BASE = {"ETH": ETH, "BTC": BTC}


def nautilus_symbol(universe_symbol: str) -> str:
    return get_instrument(universe_symbol).nautilus_symbol


def make_spot_instrument(universe_symbol: str, costs: VenueCostConfig) -> CurrencyPair:
    spec = get_instrument(universe_symbol)
    constraints = spec.constraints
    base = _BASE.get(spec.nautilus_base)
    if base is None:
        raise ValueError(f"no nautilus base currency for {universe_symbol!r}")
    return CurrencyPair(
        instrument_id=InstrumentId(symbol=Symbol(spec.nautilus_symbol), venue=NAUTILUS_VENUE),
        raw_symbol=Symbol(spec.nautilus_symbol),
        base_currency=base,
        quote_currency=USD,
        price_precision=constraints.price_precision,
        size_precision=constraints.size_precision,
        price_increment=Price(constraints.price_increment, precision=constraints.price_precision),
        size_increment=Quantity(constraints.size_increment, precision=constraints.size_precision),
        lot_size=None,
        max_quantity=Quantity(9000, precision=constraints.size_precision),
        min_quantity=Quantity(constraints.min_quantity, precision=constraints.size_precision),
        max_notional=None,
        min_notional=Money(constraints.min_notional, USD),
        max_price=Price(1_000_000, precision=constraints.price_precision),
        min_price=Price(constraints.price_increment, precision=constraints.price_precision),
        margin_init=Decimal("0"),
        margin_maint=Decimal("0"),
        maker_fee=costs.maker_fee,
        taker_fee=costs.taker_fee,
        ts_event=0,
        ts_init=0,
    )
