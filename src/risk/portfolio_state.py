"""Starea de portofoliu și regulile de rotunjire per instrument.

Nu e un snapshot de broker — e input-ul determinist al RiskEngine.evaluate().
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import yaml
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError

from src.risk.config_schema import _decimal_from_yaml

_STRICT = ConfigDict(extra="forbid")
_ALLOWED_ASSET_CLASSES = frozenset({"equity", "crypto", "fx"})

DEFAULT_MIN_NOTIONAL = Decimal("1")
DEFAULT_LOT_SIZE = Decimal("1")
DEFAULT_TICK_SIZE = Decimal("0.01")

NonNegativeDecimal = Annotated[Decimal, BeforeValidator(_decimal_from_yaml), Field(ge=0)]
PositiveDecimal = Annotated[Decimal, BeforeValidator(_decimal_from_yaml), Field(gt=0)]


class InstrumentRules(BaseModel):
    """Reguli de lot/notional pentru rotunjirea cantității. extra=forbid."""

    model_config = _STRICT

    min_notional: PositiveDecimal
    lot_size: PositiveDecimal
    tick_size: PositiveDecimal


class PortfolioState(BaseModel):
    """Expunere și metrici de risc deja realizate — niciun câmp nu vine din LLM."""

    model_config = _STRICT

    exposure_per_instrument: dict[str, NonNegativeDecimal] = Field(default_factory=dict)
    exposure_per_asset_class: dict[str, NonNegativeDecimal] = Field(default_factory=dict)
    daily_realized_loss: NonNegativeDecimal
    current_drawdown: NonNegativeDecimal
    orders_today: int = Field(ge=0)
    last_price: dict[str, PositiveDecimal] = Field(default_factory=dict)
    open_quantity: dict[str, NonNegativeDecimal] = Field(default_factory=dict)


def _optional_positive_decimal(raw: Any, default: Decimal, field_name: str) -> Decimal:
    if raw is None:
        return default
    try:
        value = _decimal_from_yaml(raw)
    except (ValueError, ArithmeticError) as exc:
        raise ValueError(f"instrument.{field_name} must be a positive number") from exc
    if value <= 0:
        raise ValueError(f"instrument.{field_name} must be a positive number")
    return value


def load_instrument_rules(
    universe_path: str | Path,
) -> tuple[dict[str, InstrumentRules], dict[str, str]]:
    """Citește regulile per simbol din universe.yaml. Câmpuri opționale → default-uri sane."""
    path = Path(universe_path)
    if not path.is_file():
        raise ValueError(f"universe.yaml missing or not a file: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("instruments"), list):
        raise ValueError("universe.yaml must contain an instruments list")

    rules: dict[str, InstrumentRules] = {}
    asset_class_by_instrument: dict[str, str] = {}
    for item in raw["instruments"]:
        if not isinstance(item, dict):
            raise ValueError("each universe instrument must be a mapping")
        symbol = item.get("symbol")
        venue = item.get("venue")
        asset_class = item.get("asset_class")
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("instrument.symbol must be a non-empty string")
        if not isinstance(venue, str) or not venue.strip():
            raise ValueError("instrument.venue must be a non-empty string")
        if asset_class not in _ALLOWED_ASSET_CLASSES:
            raise ValueError(
                f"instrument.asset_class must be one of {sorted(_ALLOWED_ASSET_CLASSES)}"
            )
        key = symbol.strip()
        try:
            instrument_rules = InstrumentRules(
                min_notional=_optional_positive_decimal(
                    item.get("min_notional"), DEFAULT_MIN_NOTIONAL, "min_notional"
                ),
                lot_size=_optional_positive_decimal(
                    item.get("lot_size"), DEFAULT_LOT_SIZE, "lot_size"
                ),
                tick_size=_optional_positive_decimal(
                    item.get("tick_size"), DEFAULT_TICK_SIZE, "tick_size"
                ),
            )
        except ValidationError as exc:
            raise ValueError(f"instrument rules invalid for {key}: {exc}") from exc
        rules[key] = instrument_rules
        asset_class_by_instrument[key] = str(asset_class)
    return rules, asset_class_by_instrument
