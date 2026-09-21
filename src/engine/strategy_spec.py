"""Interfața comună de strategie — produce doar semnale, niciodată ordine.

O `StrategySpec` primește `bars_upto_t` (deja tăiate de apelant la T — bara curentă e
ultima din listă, niciuna cu timestamp > T) și întoarce un `StrategySignal`. Nu are acces
la broker, la RiskEngine sau la cantitate — sizing-ul rămâne exclusiv `src/risk/`.
Traducerea semnalului în propunere pentru RiskEngine se face în afara acestui modul
(`src/engine/strategy_adapter.py`), care e singurul loc ce poate trimite mai departe către
execuție — și doar prin RiskEngine, niciodată direct la exchange.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.data.sources import Bar

_STRICT = ConfigDict(extra="forbid")

SignalSide = Literal["buy", "sell", "hold"]
StrategyStatus = Literal["experimental", "testing", "paper_candidate", "disabled"]


class StrategyParams(BaseModel):
    """Bază pentru parametrii unei strategii. `extra=forbid` — respinge câmpuri necunoscute."""

    model_config = _STRICT


class StrategySignal(BaseModel):
    """Ieșirea unei strategii. Fără cantitate — sizing e exclusiv RiskEngine.

    `HOLD` nu ajunge niciodată la RiskEngine (nu există nimic de evaluat). `stop_price` /
    `take_profit_price` sunt propunerile strategiei; RiskEngine le poate folosi pentru
    verificarea reward/risk, dar limitele globale de risc rămân sursa unică de adevăr
    pentru cantitate și expunere.
    """

    model_config = _STRICT

    side: SignalSide
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    stop_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    invalidation: str | None = None


def reward_risk_ratio(
    entry_price: Decimal,
    stop_price: Decimal | None,
    take_profit_price: Decimal | None,
) -> Decimal | None:
    """(target - entry) / (entry - stop) pentru un long. None dacă stop/target lipsesc sau riscul e 0."""
    if stop_price is None or take_profit_price is None:
        return None
    risk = entry_price - stop_price
    if risk <= 0:
        return None
    reward = take_profit_price - entry_price
    if reward <= 0:
        return Decimal("0")
    return reward / risk


class StrategySpec(ABC):
    """Contract comun pentru strategiile rule-based.

    O implementare NU importă `src.execution` și nu apelează brokerul. `evaluate` trebuie
    să fie pură: nu citește nimic în afara `bars_upto_t` (verificat de
    `tests/adversarial/test_lookahead_bias.py`).
    """

    id: str
    name: str
    description: str
    hypothesis: str
    version: int
    status: StrategyStatus
    updated_at: datetime
    supported_assets: tuple[str, ...]
    supported_timeframes: tuple[str, ...]
    params: StrategyParams
    cooldown_bars: int = 0
    max_simultaneous_positions: int = 1
    # Poate doar STRÂNGE limita globală de expunere, niciodată lărgi — verificat prin
    # min(global, local) în adaptor, nu prin înlocuire.
    max_exposure_override: Decimal | None = None

    @abstractmethod
    def warmup_bars(self) -> int:
        """Numărul minim de bare înainte ca evaluate() să poată produce un semnal non-hold."""

    @abstractmethod
    def evaluate(self, bars_upto_t: list[Bar]) -> StrategySignal:
        """Pur. `bars_upto_t[-1]` e bara curentă T; nicio bară din listă nu are timestamp > T."""
