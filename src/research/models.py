"""Modele de graniță pentru research (design-research-financiar.md §6.1).

Toate au extra="forbid" — un câmp neașteptat (ex. injectat de o sursă externă)
e respins la validare, nu ignorat silențios.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_STRICT = ConfigDict(extra="forbid")

SourceKind = Literal["rss", "api", "html_crawler", "browser_automation"]
RobotsTxtStatus = Literal["allowed", "disallowed", "not_applicable_api", "pending"]
ReviewStatus = Literal[
    "pending",
    "pending_manual_tos_review",
    "docs_reviewed_terms_pending",
    "reviewed",
    "reviewed_with_dynamic_limit",
]
RedistributionAllowed = Literal["yes", "no", "unknown"]
ACTIVE_REVIEW_STATUSES = frozenset({"reviewed", "reviewed_with_dynamic_limit"})
DocumentCategory = Literal[
    "news",
    "earnings",
    "filing",
    "macro_indicator",
    "market_analysis",
    "sentiment",
    "geopolitical",
    "protocol_upgrade",
    "token_unlock",
    "governance",
    "listing",
    "onchain_alert",
    "funding_regime",
    "regulatory",
]
ImpactMagnitude = Literal["low", "medium", "high"]
ImpactDirection = Literal["bullish", "bearish", "neutral", "unclear"]


class SourceConfig(BaseModel):
    """Intrare de registry. Prezența în YAML nu activează ingestia — vezi `is_fetchable`."""

    model_config = _STRICT

    source_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: SourceKind
    base_url: str = Field(min_length=1)
    credibility_score: float = Field(ge=0.0, le=1.0)
    robots_txt_status: RobotsTxtStatus
    tos_reviewed_at: datetime | None = None
    rate_limit_per_min: int | None = Field(default=None, gt=0)
    min_request_interval_s: float | None = Field(default=None, gt=0)
    review_status: ReviewStatus = "pending"
    docs_url: str | None = None
    terms_url: str | None = None
    robots_url: str | None = None
    rate_limit_source: str | None = None
    rate_limit_notes: str | None = None
    last_verified_at: datetime | None = None
    attribution_required: bool = False
    redistribution_allowed: RedistributionAllowed = "unknown"
    retention_policy: str = "metadata_and_summary_only"
    notes: list[str] = Field(default_factory=list)

    @field_validator("tos_reviewed_at", "last_verified_at", mode="before")
    @classmethod
    def _date_only_to_utc(cls, value: object) -> object:
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
        if isinstance(value, str) and len(value) == 10 and value[4] == "-":
            parsed = date.fromisoformat(value)
            return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)
        return value

    def is_fetchable(self) -> bool:
        return (
            self.tos_reviewed_at is not None
            and self.review_status in ACTIVE_REVIEW_STATUSES
        )


class RawDocument(BaseModel):
    """Ieșirea unui Connector, înainte de extracție/normalizare."""

    model_config = _STRICT

    url: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    fetched_at: datetime
    raw_payload_ref: str = Field(min_length=1)
    title: str | None = None
    summary: str | None = None


class ResearchDocument(BaseModel):
    """Document canonic, persistat în SQLite sau PostgreSQL."""

    model_config = _STRICT

    doc_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    author: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime
    event_date: datetime | None = None
    assets_mentioned: list[str]
    category: DocumentCategory
    extracted_text: str = Field(min_length=1)
    raw_payload_ref: str | None = None
    summary: str | None = None
    sentiment_score: float | None = Field(default=None, ge=-1.0, le=1.0)
    impact_magnitude: ImpactMagnitude | None = None
    impact_direction: ImpactDirection | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    data_quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    last_verified_at: datetime
    content_hash: str = Field(min_length=1)
