"""Modele de graniță pentru research (design-research-financiar.md §6.1).

Toate au extra="forbid" — un câmp neașteptat (ex. injectat de o sursă externă)
e respins la validare, nu ignorat silențios.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")

SourceKind = Literal["rss", "api", "html_crawler", "browser_automation"]
RobotsTxtStatus = Literal["allowed", "disallowed", "not_applicable_api"]
DocumentCategory = Literal[
    "news",
    "earnings",
    "filing",
    "macro_indicator",
    "market_analysis",
    "sentiment",
    "geopolitical",
]
ImpactMagnitude = Literal["low", "medium", "high"]
ImpactDirection = Literal["bullish", "bearish", "neutral", "unclear"]


class SourceConfig(BaseModel):
    """Intrare de registry. `tos_reviewed_at` e obligatoriu — vezi Regula absolută 1."""

    model_config = _STRICT

    source_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: SourceKind
    base_url: str = Field(min_length=1)
    credibility_score: float = Field(ge=0.0, le=1.0)
    robots_txt_status: RobotsTxtStatus
    tos_reviewed_at: datetime
    rate_limit_per_min: int | None = Field(default=None, gt=0)


class RawDocument(BaseModel):
    """Ieșirea unui Connector, înainte de extracție/normalizare."""

    model_config = _STRICT

    url: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    fetched_at: datetime
    raw_payload_ref: str = Field(min_length=1)


class ResearchDocument(BaseModel):
    """Rândul normalizat, persistat în metadata.db — vezi design §5 pentru DDL echivalent."""

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
    summary: str | None = None
    sentiment_score: float | None = Field(default=None, ge=-1.0, le=1.0)
    impact_magnitude: ImpactMagnitude | None = None
    impact_direction: ImpactDirection | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    last_verified_at: datetime
    content_hash: str = Field(min_length=1)
