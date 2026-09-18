"""Tipuri de propunere pe partea engine/ — duplicat structural al llm.schema.

Definite independent, fără niciun import din src.llm (design §7, Opțiunea B).
Sincronizarea cu llm.schema e verificată de tests/integration/test_proposal_contract.py.
"""

from __future__ import annotations

from datetime import datetime
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


class ParsedProposal(BaseModel):
    """Deserializare locală a JSON-ului HTTP — identic structural cu LLMProposal."""

    model_config = _STRICT

    instrument: str = Field(min_length=1)
    direction: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)


class RejectedProposal(BaseModel):
    """Respingere primită pe HTTP sau produsă de client (timeout/erori de transport)."""

    model_config = _STRICT

    reason: RejectReason
    raw_output: str


class ProposalContext(BaseModel):
    """Context minim pentru Faza 2. Datele de piață reale vin din data/ în Faza 4."""

    model_config = _STRICT

    instrument: str = Field(min_length=1)
    as_of: datetime
    market_summary: str
    external_context: str | None = None
