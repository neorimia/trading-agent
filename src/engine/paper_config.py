"""Config paper trading — validare hard, fără fallback live."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

_STRICT = ConfigDict(extra="forbid")


class PaperTradingConfig(BaseModel):
    model_config = _STRICT

    path: Literal["B"]
    dry_run: bool
    venue: Literal["KRAKEN"]
    instrument: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    starting_cash: Decimal = Field(gt=0)
    lookback_bars: int = Field(gt=0)
    fast_ema_period: int = Field(gt=0)
    slow_ema_period: int = Field(gt=0)
    approval_timeout_s: float = Field(gt=0)
    stale_data_threshold_s: float = Field(gt=0)
    heartbeat_threshold_s: float = Field(gt=0)
    session_count_target: int = Field(gt=0)

    @field_validator("dry_run")
    @classmethod
    def _dry_run_must_be_true(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("dry_run must be true — live execution is forbidden in Faza 5")
        return value

    @field_validator("slow_ema_period")
    @classmethod
    def _slow_gt_fast(cls, value: int, info):  # noqa: ANN001
        fast = info.data.get("fast_ema_period")
        if fast is not None and value <= fast:
            raise ValueError("slow_ema_period must be greater than fast_ema_period")
        return value


def load_paper_trading_config(path: str | Path) -> PaperTradingConfig:
    config_path = Path(path)
    if not config_path.is_file():
        raise ValueError(f"paper_trading.yaml missing or not a file: {config_path}")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("paper_trading.yaml must contain a mapping")
    try:
        return PaperTradingConfig.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"paper_trading.yaml invalid: {exc}") from exc
