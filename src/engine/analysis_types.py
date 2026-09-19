"""Tipuri de analiză pe partea engine/ — duplicat structural al llm.schema.

Definite independent, fără niciun import din src.llm.
Sincronizarea e verificată de tests/integration/test_analysis_contract.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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


class AnalysisDataSource(BaseModel):
    model_config = _STRICT

    url: str = Field(min_length=1)
    as_of: datetime | None = None
    content_hash: str | None = None


class AnalysisAuditMetadata(BaseModel):
    model_config = _STRICT

    model_name: str = Field(min_length=1)
    prompt_hash: str = Field(min_length=1)
    facts_bundle_hash: str = Field(min_length=1)
    temperature: float
    schema_version: str = Field(min_length=1)


class ParsedAnalysis(BaseModel):
    """Deserializare locală a JSON-ului HTTP — identic structural cu LLMAnalysis."""

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
    data_quality_score: float = Field(ge=0.0, le=1.0)
    uncertainty: str = Field(min_length=1)
    recommended_action: RecommendedAction
    action_type: ActionType
    position_size_suggestion: None = None
    required_human_approval: bool
    expiry_time: datetime
    audit_metadata: AnalysisAuditMetadata


class RejectedAnalysis(BaseModel):
    model_config = _STRICT

    reason: RejectReason
    raw_output: str


class AnalysisContext(BaseModel):
    """Context trimis către POST /analyze. facts_bundle e determinist."""

    model_config = _STRICT

    instrument: str = Field(min_length=1)
    as_of: datetime
    analysis_type: AnalysisType
    timeframe: str = Field(min_length=1)
    facts_bundle: dict[str, Any]
    external_context: str | None = None


class AnalysisRunResponse(BaseModel):
    """Nivel 1: raport de research. is_order e mereu False."""

    model_config = _STRICT

    is_order: Literal[False] = False
    facts_bundle: dict[str, Any]
    analysis: ParsedAnalysis | None = None
    rejected: RejectedAnalysis | None = None
