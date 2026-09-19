from __future__ import annotations

from datetime import datetime, timezone

from src.engine.analysis_types import ParsedAnalysis
from src.engine.signal_normalize import normalize_analysis


def _analysis() -> ParsedAnalysis:
    return ParsedAnalysis.model_validate(
        {
            "asset": "ETHUSD",
            "timestamp": datetime(2026, 9, 18, tzinfo=timezone.utc),
            "timeframe": "1d",
            "analysis_type": "technical",
            "factual_summary": "EMA cross up.",
            "data_sources": [{"url": "kraken:ohlc", "as_of": "2026-09-18T00:00:00+00:00", "content_hash": "x"}],
            "bullish_case": "hold above slow",
            "bearish_case": "lose slow",
            "neutral_case": "range",
            "key_assumptions": ["spot"],
            "catalysts": ["unknown"],
            "risks": ["liquidity"],
            "invalidation_conditions": ["close below slow"],
            "confidence_score": 0.9,
            "data_quality_score": 0.8,
            "uncertainty": "no funding",
            "recommended_action": "propose_long",
            "action_type": "proposal_candidate",
            "position_size_suggestion": None,
            "required_human_approval": True,
            "expiry_time": datetime(2026, 9, 19, tzinfo=timezone.utc),
            "audit_metadata": {
                "model_name": "qwen3:8b",
                "prompt_hash": "aa",
                "facts_bundle_hash": "bb",
                "temperature": 0.0,
                "schema_version": "analysis.v1",
            },
        }
    )


def test_level1_normalizer_never_emits_a_proposal() -> None:
    assert normalize_analysis(_analysis()) is None
