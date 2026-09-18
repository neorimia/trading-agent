"""Contractul JSON al procesului LLM — modele pure, zero I/O.

Fără câmp de mărime poziție, preț sau limită de risc (design §4.1–4.2).
Nu e importat din engine/risk/execution — izolare totală (design §7).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Direction = Literal["long", "avoid", "exit"]
RejectReason = Literal[
    "schema_invalid",
    "instrument_not_in_universe",
    "timeout",
    "model_error",
]

_STRICT = ConfigDict(extra="forbid")


class LLMProposal(BaseModel):
    """Ieșirea validă a stratului LLM. extra=forbid: câmpuri necunoscute → invalid."""

    model_config = _STRICT

    instrument: str = Field(min_length=1)
    direction: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)


class RejectedProposal(BaseModel):
    """Output invalid sau în afara universului — păstrat brut, niciodată reparat."""

    model_config = _STRICT

    reason: RejectReason
    raw_output: str
