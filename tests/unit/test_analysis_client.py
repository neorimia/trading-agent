"""Client HTTP către POST /analyze — fără tipuri din src.llm."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from src.engine.analysis_client import LLMAnalysisClient
from src.engine.analysis_types import AnalysisContext, ParsedAnalysis, RejectedAnalysis


def _context() -> AnalysisContext:
    return AnalysisContext(
        instrument="ETHUSD",
        as_of=datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc),
        analysis_type="technical",
        timeframe="1d",
        facts_bundle={"close": "2410"},
        external_context=None,
    )


def _client(handler) -> LLMAnalysisClient:
    http = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://127.0.0.1:8765",
    )
    return LLMAnalysisClient(
        base_url="http://127.0.0.1:8765",
        http_client=http,
    )


def _valid_body() -> dict:
    return {
        "asset": "ETHUSD",
        "timestamp": "2026-09-18T12:00:00+00:00",
        "timeframe": "1d",
        "analysis_type": "technical",
        "factual_summary": "EMA fast above slow.",
        "data_sources": [{"url": "kraken:ohlc"}],
        "bullish_case": "hold",
        "bearish_case": "break",
        "neutral_case": "range",
        "key_assumptions": ["spot"],
        "catalysts": ["unknown"],
        "risks": ["liq"],
        "invalidation_conditions": ["close below slow"],
        "confidence_score": 0.4,
        "data_quality_score": 0.6,
        "uncertainty": "no funding",
        "recommended_action": "hold",
        "action_type": "research_only",
        "position_size_suggestion": None,
        "required_human_approval": True,
        "expiry_time": "2026-09-19T12:00:00+00:00",
        "audit_metadata": {
            "model_name": "qwen3:8b",
            "prompt_hash": "aa",
            "facts_bundle_hash": "bb",
            "temperature": 0.0,
            "schema_version": "analysis.v1",
        },
    }


def test_request_analysis_hits_analyze_not_propose() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/analyze"
        return httpx.Response(200, json=_valid_body())

    result = _client(handler).request_analysis(_context())
    assert isinstance(result, ParsedAnalysis)
    assert type(result).__module__ == "src.engine.analysis_types"
    assert result.position_size_suggestion is None


def test_request_analysis_parses_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"reason": "schema_invalid", "raw_output": "nope"})

    result = _client(handler).request_analysis(_context())
    assert isinstance(result, RejectedAnalysis)
    assert result.reason == "schema_invalid"


def test_request_analysis_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("late")

    result = _client(handler).request_analysis(_context(), timeout_s=1.0)
    assert isinstance(result, RejectedAnalysis)
    assert result.reason == "timeout"


def test_size_field_from_http_is_schema_invalid() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = _valid_body()
        body["position_size_suggestion"] = 99
        return httpx.Response(200, json=body)

    result = _client(handler).request_analysis(_context())
    assert isinstance(result, RejectedAnalysis)
    assert result.reason == "schema_invalid"
