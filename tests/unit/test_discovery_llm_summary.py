"""Narativul LLM peste candidați de discovery — guardrail-uri (design §4, §5, Faza 2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.discovery.llm_summary import contains_forbidden_language, summarize_candidate
from src.discovery.models import AssetCandidate, CandidateFactors, SourceRef
from src.engine.analysis_types import AnalysisAuditMetadata, ParsedAnalysis, RejectedAnalysis

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


def _parsed_analysis(**overrides: object) -> ParsedAnalysis:
    defaults = dict(
        asset="XXBTZUSD",
        timestamp=_NOW,
        timeframe="swing (days-weeks)",
        analysis_type="discovery",
        factual_summary="Liquidity and spread pass the eligibility filters.",
        data_sources=[],
        bullish_case="Liquidity score is above the peer median.",
        bearish_case="Volatility is elevated versus the reference window.",
        neutral_case="Correlation with BTC limits diversification benefit.",
        key_assumptions=["Kraken spot only"],
        catalysts=["unknown"],
        risks=["operational risk score above median"],
        invalidation_conditions=["exchange status leaves online"],
        confidence_score=0.4,
        data_quality_score=0.8,
        uncertainty="News sentiment and catalyst score are not yet computed.",
        recommended_action="research_more",
        action_type="research_only",
        position_size_suggestion=None,
        required_human_approval=True,
        expiry_time=_NOW + timedelta(hours=24),
        audit_metadata=AnalysisAuditMetadata(
            model_name="qwen3:8b",
            prompt_hash="aa",
            facts_bundle_hash="bb",
            temperature=0.0,
            schema_version="analysis.v1",
        ),
    )
    defaults.update(overrides)
    return ParsedAnalysis.model_validate(defaults)


def test_contains_forbidden_language_detects_certainty_claims() -> None:
    assert contains_forbidden_language("This is a guaranteed win.") == "guaranteed"
    assert contains_forbidden_language("Va crește sigur pana maine.") is not None
    assert contains_forbidden_language("Volatility is elevated versus peers.") is None


def test_summarize_candidate_accepts_clean_narrative() -> None:
    candidate = _candidate()
    analysis = _parsed_analysis()

    updated = summarize_candidate(candidate, lambda _ctx: analysis, now=_NOW)

    assert updated.bullish_case == [analysis.bullish_case]
    assert updated.bearish_case == [analysis.bearish_case]
    assert updated.neutral_case == [analysis.neutral_case]
    assert updated.invalidation_conditions == analysis.invalidation_conditions
    assert updated.sources[-1].source_id == "llm_discovery_summary"
    # Deterministic scores are never overwritten by the LLM's own scores.
    assert updated.opportunity_score == candidate.opportunity_score
    assert updated.risk_score == candidate.risk_score
    assert updated.confidence_score == candidate.confidence_score
    assert updated.data_quality_score == candidate.data_quality_score


def test_summarize_candidate_rejects_forbidden_phrase_without_mutating_narrative() -> None:
    candidate = _candidate()
    analysis = _parsed_analysis(bullish_case="This will definitely go up.")

    updated = summarize_candidate(candidate, lambda _ctx: analysis, now=_NOW)

    assert updated.bullish_case == []
    assert updated.bearish_case == []
    assert updated.neutral_case == []
    assert updated.sources == candidate.sources
    assert "llm_summary_rejected:forbidden_phrase" in updated.missing_data


def test_summarize_candidate_rejects_llm_rejection_without_guessing() -> None:
    candidate = _candidate()
    rejected = RejectedAnalysis(reason="timeout", raw_output="")

    updated = summarize_candidate(candidate, lambda _ctx: rejected, now=_NOW)

    assert updated.bullish_case == []
    assert updated.sources == candidate.sources
    assert "llm_summary_rejected:timeout" in updated.missing_data
