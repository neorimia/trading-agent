"""VenueRegistry — un singur loc pentru simboluri, constraints, venue de execuție."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.data.venue_registry import (
    EXECUTION_VENUE,
    NAUTILUS_VENUE_NAME,
    UNIVERSE_TO_BINANCE,
    UNIVERSE_TO_KRAKEN,
    constraints_for,
    execution_pair,
    get_instrument,
    historical_symbol,
    nautilus_symbol,
)


def test_execution_venue_is_kraken() -> None:
    assert EXECUTION_VENUE == "KRAKEN"
    assert NAUTILUS_VENUE_NAME == "KRAKEN"
    assert get_instrument("ETHUSD").execution_venue == "KRAKEN"


def test_symbol_maps_are_centralized() -> None:
    assert UNIVERSE_TO_KRAKEN["ETHUSD"] == "ETHUSD"
    assert UNIVERSE_TO_BINANCE["ETHUSD"] == "ETHUSDT"
    assert execution_pair("BTCUSD") == "BTCUSD"
    assert historical_symbol("ETHUSD", "BINANCE") == "ETHUSDT"
    assert historical_symbol("ETHUSD", "KRAKEN") == "ETHUSD"
    assert nautilus_symbol("ETHUSD") == "ETHUSD"


def test_constraints_match_universe_defaults() -> None:
    eth = constraints_for("ETHUSD")
    assert eth.min_notional == Decimal("10")
    assert eth.lot_size > 0
    assert eth.tick_size > 0


def test_unknown_symbol_rejected() -> None:
    with pytest.raises(ValueError, match="no venue mapping"):
        get_instrument("AAPL")
