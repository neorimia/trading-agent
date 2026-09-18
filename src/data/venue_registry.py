"""Registru unic de venue: simboluri, constraints, sursă istorică vs execuție.

Execuția live/paper e KRAKEN. Binance rămâne doar backfill opțional pentru
istoric lung (paginare klines). Backtestul Nautilus simulează venue-ul de
execuție, nu vendor-ul de istoric.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

ExecutionVenue = Literal["KRAKEN"]
HistoricalSource = Literal["KRAKEN", "BINANCE"]

EXECUTION_VENUE: ExecutionVenue = "KRAKEN"
NAUTILUS_VENUE_NAME = "KRAKEN"
# Istoric lung: Binance public klines. Kraken OHLC public ~720 lumânări.
DEFAULT_HISTORICAL_SOURCE: HistoricalSource = "BINANCE"


@dataclass(frozen=True)
class InstrumentConstraints:
    min_notional: Decimal
    lot_size: Decimal
    tick_size: Decimal
    min_quantity: Decimal
    price_precision: int
    size_precision: int
    price_increment: Decimal
    size_increment: Decimal


@dataclass(frozen=True)
class VenueInstrument:
    universe_symbol: str
    execution_venue: ExecutionVenue
    kraken_pair: str
    binance_symbol: str
    nautilus_symbol: str
    nautilus_base: str
    constraints: InstrumentConstraints


_ETH = InstrumentConstraints(
    min_notional=Decimal("10"),
    lot_size=Decimal("0.0001"),
    tick_size=Decimal("0.01"),
    min_quantity=Decimal("0.00001"),
    price_precision=2,
    size_precision=5,
    price_increment=Decimal("0.01"),
    size_increment=Decimal("0.00001"),
)
_BTC = InstrumentConstraints(
    min_notional=Decimal("10"),
    lot_size=Decimal("0.0001"),
    tick_size=Decimal("0.01"),
    min_quantity=Decimal("0.000001"),
    price_precision=2,
    size_precision=6,
    price_increment=Decimal("0.01"),
    size_increment=Decimal("0.000001"),
)

_INSTRUMENTS: dict[str, VenueInstrument] = {
    "ETHUSD": VenueInstrument(
        universe_symbol="ETHUSD",
        execution_venue="KRAKEN",
        kraken_pair="ETHUSD",
        binance_symbol="ETHUSDT",
        nautilus_symbol="ETHUSD",
        nautilus_base="ETH",
        constraints=_ETH,
    ),
    "BTCUSD": VenueInstrument(
        universe_symbol="BTCUSD",
        execution_venue="KRAKEN",
        kraken_pair="BTCUSD",
        binance_symbol="BTCUSDT",
        nautilus_symbol="BTCUSD",
        nautilus_base="BTC",
        constraints=_BTC,
    ),
}

UNIVERSE_TO_KRAKEN = {
    spec.universe_symbol: spec.kraken_pair for spec in _INSTRUMENTS.values()
}
UNIVERSE_TO_BINANCE = {
    spec.universe_symbol: spec.binance_symbol for spec in _INSTRUMENTS.values()
}


def get_instrument(universe_symbol: str) -> VenueInstrument:
    spec = _INSTRUMENTS.get(universe_symbol)
    if spec is None:
        raise ValueError(f"no venue mapping for {universe_symbol!r}")
    return spec


def execution_pair(universe_symbol: str) -> str:
    return get_instrument(universe_symbol).kraken_pair


def historical_symbol(universe_symbol: str, source: HistoricalSource) -> str:
    spec = get_instrument(universe_symbol)
    if source == "KRAKEN":
        return spec.kraken_pair
    return spec.binance_symbol


def nautilus_symbol(universe_symbol: str) -> str:
    return get_instrument(universe_symbol).nautilus_symbol


def constraints_for(universe_symbol: str) -> InstrumentConstraints:
    return get_instrument(universe_symbol).constraints


def listed_crypto_symbols() -> tuple[str, ...]:
    return tuple(_INSTRUMENTS)
