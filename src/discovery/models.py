"""Modele de graniță pentru asset discovery (design-asset-discovery-research.md §5).

Toate au extra="forbid" — mirror pe src/research/models.py. Faza 1 e crypto-only,
fără LLM: bullish_case/bearish_case/neutral_case rămân liste goale (populate în Faza 2),
iar `requires_human_review` e hardcodat True — niciun candidat nu ocolește aprobarea.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")

AssetClass = Literal["crypto", "equity"]
CandidateStatus = Literal["research", "watchlist", "trade_setup"]
InstrumentStatus = Literal["online", "cancel_only", "post_only", "limit_only"]


class DiscoveredInstrument(BaseModel):
    """O intrare din `GET /0/public/AssetPairs` — universul brut, înainte de filtrare."""

    model_config = _STRICT

    exchange_pair: str = Field(min_length=1)
    base: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    status: InstrumentStatus
    ordermin: Decimal | None = None
    costmin: Decimal | None = None


class InstrumentSnapshot(BaseModel):
    """Preț/volum/spread curent (`GET /0/public/Ticker`) pentru un `exchange_pair`."""

    model_config = _STRICT

    exchange_pair: str = Field(min_length=1)
    last_price: Decimal
    bid: Decimal
    ask: Decimal
    volume_24h: Decimal


class HistoricalStats(BaseModel):
    """Factori derivați din OHLC (`GET /0/public/OHLC`) pentru un `exchange_pair`."""

    model_config = _STRICT

    exchange_pair: str = Field(min_length=1)
    listing_age_days: int = Field(ge=0)
    history_days_available: int = Field(ge=0)
    history_days_requested: int = Field(ge=1)
    daily_closes: list[float]
    daily_volumes: list[float]


class FilterResult(BaseModel):
    """Rezultatul unei reguli de eligibilitate — mereu populat, și la passed=True (audit)."""

    model_config = _STRICT

    rule_id: str = Field(min_length=1)
    passed: bool
    reason: str = Field(min_length=1)
    observed_value: str | None = None


class CandidateFactors(BaseModel):
    """Factori deterministici (§2.1, §4.1) — Faza 1 crypto-only: fără news/catalyst."""

    model_config = _STRICT

    notional_volume_24h_usd: Decimal
    spread_bps: float
    liquidity_score: float = Field(ge=0.0, le=1.0)
    spread_score: float = Field(ge=0.0, le=1.0)
    volatility: float | None = None
    data_quality_score: float = Field(ge=0.0, le=1.0)
    operational_risk_score: float = Field(ge=0.0, le=1.0)
    correlation_btc: float | None = Field(default=None, ge=-1.0, le=1.0)
    correlation_eth: float | None = Field(default=None, ge=-1.0, le=1.0)
    min_order_notional_usd: Decimal | None = None
    listing_age_days: int = Field(ge=0)
    exchange_status: InstrumentStatus


class SourceRef(BaseModel):
    model_config = _STRICT

    source_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    fetched_at: datetime


class AssetCandidate(BaseModel):
    """Candidat de research/watchlist — niciodată o comandă (design §1, invariant arhitectural)."""

    model_config = _STRICT

    asset: str = Field(min_length=1)
    asset_class: AssetClass
    exchange: str = Field(min_length=1)
    timestamp: datetime
    research_horizon: str
    candidate_status: CandidateStatus
    opportunity_score: float = Field(ge=0.0, le=1.0)
    risk_score: float = Field(ge=0.0, le=1.0)
    confidence_score: float = Field(ge=0.0, le=1.0)
    data_quality_score: float = Field(ge=0.0, le=1.0)
    factors: CandidateFactors
    bullish_case: list[str] = Field(default_factory=list)
    bearish_case: list[str] = Field(default_factory=list)
    neutral_case: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    expires_at: datetime
    requires_human_review: bool = True


class RejectedCandidate(BaseModel):
    """Instrument respins de pipeline — rezultatul nu dispare silențios (§3, mirror RejectedProposal)."""

    model_config = _STRICT

    asset: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    evaluated_at: datetime
    filter_results: list[FilterResult]


class DiscoveryRun(BaseModel):
    """Output-ul unei rulări de discovery — persistat JSONL, un fișier per zi (§5, §6)."""

    model_config = _STRICT

    run_at: datetime
    exchange: str = Field(min_length=1)
    candidates: list[AssetCandidate]
    rejected: list[RejectedCandidate]
