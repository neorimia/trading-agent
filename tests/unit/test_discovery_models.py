"""Modele discovery — extra=forbid, requires_human_review hardcodat True (design §5)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.discovery.models import AssetCandidate, CandidateFactors, SourceRef

_NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)


def _factors() -> CandidateFactors:
    return CandidateFactors(
        notional_volume_24h_usd="1000000",
        spread_bps=5.0,
        liquidity_score=0.8,
        spread_score=0.9,
        volatility=0.02,
        data_quality_score=1.0,
        operational_risk_score=0.1,
        correlation_btc=0.5,
        correlation_eth=0.4,
        min_order_notional_usd="10",
        listing_age_days=400,
        exchange_status="online",
    )


def _candidate(**overrides: object) -> AssetCandidate:
    defaults = dict(
        asset="XXBTZUSD",
        asset_class="crypto",
        exchange="KRAKEN",
        timestamp=_NOW,
        research_horizon="swing (days-weeks)",
        candidate_status="research",
        opportunity_score=0.7,
        risk_score=0.2,
        confidence_score=0.8,
        data_quality_score=1.0,
        factors=_factors(),
        sources=[SourceRef(source_id="kraken_public_api", url="https://api.kraken.com/0/public", fetched_at=_NOW)],
        expires_at=_NOW + timedelta(hours=24),
    )
    defaults.update(overrides)
    return AssetCandidate.model_validate(defaults)


def test_asset_candidate_defaults_require_human_review() -> None:
    candidate = _candidate()
    assert candidate.requires_human_review is True
    assert candidate.bullish_case == []
    assert candidate.missing_data == []


def test_asset_candidate_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        _candidate(injected_field="ignore me")




def test_candidate_factors_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CandidateFactors(
            notional_volume_24h_usd="1",
            spread_bps=1.0,
            liquidity_score=0.5,
            spread_score=0.5,
            data_quality_score=0.5,
            operational_risk_score=0.1,
            listing_age_days=1,
            exchange_status="online",
            unexpected="nope",
        )
