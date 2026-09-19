"""Registru unic de venue: simboluri, constraints, sursă istorică vs execuție.

Instrumentele cu plumbing Kraken (§_INSTRUMENTS) execută live/paper pe KRAKEN.
Orice alt simbol din universe.yaml (ex. echities) e research-only —
`execution_venue == "NONE"` — nu o eroare "necunoscut": apartenența la
universul allowlist-at se validează separat (`instrument_not_in_universe`),
nu aici. Binance rămâne doar backfill opțional pentru istoric lung crypto.
Backtestul Nautilus simulează venue-ul de execuție, nu vendor-ul de istoric.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

ExecutionVenue = Literal["KRAKEN", "NONE"]
HistoricalSource = Literal["KRAKEN", "BINANCE"]

EXECUTION_VENUE: ExecutionVenue = "KRAKEN"
NAUTILUS_VENUE_NAME = "KRAKEN"
# Istoric lung: Binance public klines. Kraken OHLC public ~720 lumânări.
DEFAULT_HISTORICAL_SOURCE: HistoricalSource = "BINANCE"


class NoExecutionVenue(ValueError):
    """Instrumentul e research-only (`execution_venue == "NONE"`) — fără plumbing de execuție."""


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
    kraken_pair: str | None = None
    binance_symbol: str | None = None
    nautilus_symbol: str | None = None
    nautilus_base: str | None = None
    constraints: InstrumentConstraints | None = None


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
    """Rezolvă plumbing-ul de execuție pentru un simbol.

    Simbolurile fără plumbing Kraken cunoscut sunt research-only
    (`execution_venue == "NONE"`), nu o eroare — apartenența la universul
    allowlist-at (universe.yaml) se validează în altă parte.
    """
    spec = _INSTRUMENTS.get(universe_symbol)
    if spec is not None:
        return spec
    return VenueInstrument(universe_symbol=universe_symbol, execution_venue="NONE")


def execution_pair(universe_symbol: str) -> str:
    spec = get_instrument(universe_symbol)
    if spec.kraken_pair is None:
        raise NoExecutionVenue(f"{universe_symbol!r} has no execution venue (research-only)")
    return spec.kraken_pair


def historical_symbol(universe_symbol: str, source: HistoricalSource) -> str:
    spec = get_instrument(universe_symbol)
    symbol = spec.kraken_pair if source == "KRAKEN" else spec.binance_symbol
    if symbol is None:
        raise NoExecutionVenue(f"{universe_symbol!r} has no execution venue (research-only)")
    return symbol


def nautilus_symbol(universe_symbol: str) -> str:
    spec = get_instrument(universe_symbol)
    if spec.nautilus_symbol is None:
        raise NoExecutionVenue(f"{universe_symbol!r} has no execution venue (research-only)")
    return spec.nautilus_symbol


def constraints_for(universe_symbol: str) -> InstrumentConstraints:
    spec = get_instrument(universe_symbol)
    if spec.constraints is None:
        raise NoExecutionVenue(f"{universe_symbol!r} has no execution venue (research-only)")
    return spec.constraints


def listed_crypto_symbols() -> tuple[str, ...]:
    return tuple(_INSTRUMENTS)
