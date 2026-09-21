"""Contractul JSON al procesului LLM — modele pure, zero I/O.

Fără câmp de mărime poziție, preț sau limită de risc (design §4.1–4.2).
Nu e importat din engine/risk/execution — izolare totală (design §7).

LLMProposal rămâne poarta îngustă către risc. LLMAnalysis e doar research (Nivel 1).
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
AnalysisType = Literal[
    "priced_in",
    "technical",
    "news_impact",
    "stress",
    "backtest",
    "trade_review",
    "daily_plan",
    "discovery",
]
RecommendedAction = Literal[
    "hold",
    "reduce_risk",
    "research_more",
    "propose_long",
    "propose_exit",
]
ActionType = Literal["research_only", "alert", "proposal_candidate"]
ANALYSIS_SCHEMA_VERSION = "analysis.v1"

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


class AnalysisDataSource(BaseModel):
    """Citată de analiză. url poate fi un pointer intern (ex. kraken:ohlc)."""

    model_config = _STRICT

    url: str = Field(min_length=1)
    as_of: datetime | None = None
    content_hash: str | None = None


class AnalysisAuditMetadata(BaseModel):
    """Completat de serviciu, nu de model."""

    model_config = _STRICT

    model_name: str = Field(min_length=1)
    prompt_hash: str = Field(min_length=1)
    facts_bundle_hash: str = Field(min_length=1)
    temperature: float
    schema_version: str = Field(min_length=1)


class LLMAnalysisDraft(BaseModel):
    """Output-ul constrâns al modelului — fără audit_metadata, size obligatoriu null."""

    model_config = _STRICT

    asset: str = Field(min_length=1)
    timestamp: datetime
    timeframe: str = Field(min_length=1)
    analysis_type: AnalysisType
    factual_summary: str = Field(min_length=1)
    data_sources: list[AnalysisDataSource]
    bullish_case: str = Field(min_length=1)
    bearish_case: str = Field(min_length=1)
    neutral_case: str = Field(min_length=1)
    key_assumptions: list[str]
    catalysts: list[str]
    risks: list[str]
    invalidation_conditions: list[str]
    confidence_score: float = Field(ge=0.0, le=1.0)
    data_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    uncertainty: str = Field(min_length=1)
    recommended_action: RecommendedAction
    action_type: ActionType = "research_only"
    position_size_suggestion: None = None
    required_human_approval: bool = True
    expiry_time: datetime | None = None


class LLMAnalysis(LLMAnalysisDraft):
    """Raport de research. Nu e ordin și nu conține mărime de poziție."""

    expiry_time: datetime
    audit_metadata: AnalysisAuditMetadata


class RejectedAnalysis(BaseModel):
    """Analiză invalidă — păstrată brută, niciodată reparată."""

    model_config = _STRICT

    reason: RejectReason
    raw_output: str
