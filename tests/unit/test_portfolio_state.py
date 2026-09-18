"""load_instrument_rules — câmpuri opționale din universe.yaml au default-uri sane."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from src.risk.portfolio_state import (
    DEFAULT_LOT_SIZE,
    DEFAULT_MIN_NOTIONAL,
    DEFAULT_TICK_SIZE,
    load_instrument_rules,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_real_universe_loads_explicit_rules() -> None:
    rules, classes = load_instrument_rules(REPO_ROOT / "config" / "universe.yaml")
    assert set(rules) == {"AAPL", "MSFT", "ETHUSD", "BTCUSD"}
    assert classes["AAPL"] == "equity"
    assert classes["ETHUSD"] == "crypto"
    assert rules["AAPL"].lot_size == Decimal("1")
    assert rules["ETHUSD"].lot_size == Decimal("0.0001")
    assert rules["ETHUSD"].min_notional == Decimal("10")


def test_missing_optional_fields_use_defaults(tmp_path: Path) -> None:
    path = tmp_path / "universe.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "instruments": [
                    {"symbol": "AAPL", "venue": "NASDAQ", "asset_class": "equity"},
                ]
            }
        ),
        encoding="utf-8",
    )
    rules, classes = load_instrument_rules(path)
    assert classes["AAPL"] == "equity"
    assert rules["AAPL"].min_notional == DEFAULT_MIN_NOTIONAL
    assert rules["AAPL"].lot_size == DEFAULT_LOT_SIZE
    assert rules["AAPL"].tick_size == DEFAULT_TICK_SIZE


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing"):
        load_instrument_rules(tmp_path / "nope.yaml")


def test_invalid_asset_class_raises(tmp_path: Path) -> None:
    path = tmp_path / "universe.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "instruments": [
                    {"symbol": "AAPL", "venue": "NASDAQ", "asset_class": "commodity"},
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="asset_class"):
        load_instrument_rules(path)


def test_non_positive_lot_size_raises(tmp_path: Path) -> None:
    path = tmp_path / "universe.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "instruments": [
                    {
                        "symbol": "AAPL",
                        "venue": "NASDAQ",
                        "asset_class": "equity",
                        "lot_size": 0,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_instrument_rules(path)
