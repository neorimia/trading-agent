"""Schema RiskLimits — validare hard la pornire, fără fallback silențios."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import yaml
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator

_STRICT = ConfigDict(extra="forbid")


def _decimal_from_yaml(value: Any) -> Decimal:
    """YAML încarcă numere ca float; trecem prin str ca să nu pierdem precizie."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or value is None:
        raise ValueError("invalid decimal value")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        return Decimal(value)
    raise ValueError(f"cannot convert {type(value).__name__} to Decimal")


PositiveDecimal = Annotated[Decimal, BeforeValidator(_decimal_from_yaml), Field(gt=0)]
NonNegativeDecimal = Annotated[Decimal, BeforeValidator(_decimal_from_yaml), Field(ge=0)]


class CircuitBreakerLimits(BaseModel):
    model_config = _STRICT

    max_consecutive_errors: int = Field(gt=0)
    max_consecutive_losses: int = Field(gt=0)
    halt_on_unknown_order_result: bool

    @field_validator("halt_on_unknown_order_result")
    @classmethod
    def _halt_on_unknown_must_be_true(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("halt_on_unknown_order_result must be true")
        return value


class RiskLimits(BaseModel):
    """Limite imutabile pe durata rulării. Extra fields interzise.

    Câmpurile noi (risc/tranzacție, R:R, spread, lichiditate, expunere corelată) sunt
    opționale — `None` dezactivează verificarea, păstrând compatibilitate cu fișiere
    `risk_limits.yaml` mai vechi care nu le au. Când sunt setate, strâng limitele
    existente; nu le pot niciodată lărgi (nu există cale de a crește un cap global
    printr-un câmp nou).
    """

    model_config = _STRICT

    max_notional_per_order: PositiveDecimal
    max_exposure_per_instrument: PositiveDecimal
    max_exposure_per_asset_class: PositiveDecimal
    max_daily_loss: PositiveDecimal
    max_drawdown: PositiveDecimal
    max_orders_per_day: int = Field(gt=0)
    circuit_breaker: CircuitBreakerLimits
    # Plafon suplimentar de risc pe o singură tranzacție (aceeași unitate ca max_daily_loss).
    # Dacă e setat, `risk_budget` e min(daily, drawdown, max_risk_per_trade).
    max_risk_per_trade: PositiveDecimal | None = None
    # Reward/risk minim cerut. Verificat doar când apelantul furnizează un raport
    # (strategiile noi îl calculează din stop/target; EMA/LLM legacy nu-l furnizează,
    # deci verificarea e omisă pentru ele — vezi docs/risk-management.md).
    min_reward_risk_ratio: PositiveDecimal | None = None
    # Spread maxim acceptat (bps) pentru a deschide o poziție nouă. Lipsa datei de spread
    # pentru instrument e tratată ca dată incompletă -> respins, nu aproximat.
    max_spread_bps: PositiveDecimal | None = None
    # Volum minim pe bară (proxy de lichiditate, nu order-book L2). Lipsa datei e tratată
    # la fel ca mai sus.
    min_bar_volume: NonNegativeDecimal | None = None
    # Expunere maximă pentru instrumente corelate (aproximat azi prin gruparea pe clasă de
    # active — vezi docs/risk-management.md pentru limitare explicită).
    max_correlated_exposure: PositiveDecimal | None = None


def load_risk_limits(path: str | Path) -> RiskLimits:
    """Încarcă și validează config/risk_limits.yaml. Lipsă/invalid → ValueError, fără default-uri."""
    limits_path = Path(path)
    if not limits_path.is_file():
        raise ValueError(f"risk_limits.yaml missing or not a file: {limits_path}")
    raw = yaml.safe_load(limits_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("risk_limits.yaml must contain a mapping")
    try:
        return RiskLimits.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"risk_limits.yaml invalid: {exc}") from exc
