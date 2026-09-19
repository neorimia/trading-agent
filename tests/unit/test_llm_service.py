"""Validare schemă: output invalid e respins, nu reparat."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from src.llm.schema import LLMAnalysis, LLMProposal, RejectedAnalysis, RejectedProposal
from src.llm.service import (
    AnalysisInput,
    ModelConfig,
    ProposalInput,
    generate_analysis,
    generate_proposal,
    load_universe,
    parse_analysis_draft,
    parse_proposal,
    strip_think_blocks,
    validate_against_universe,
)


def test_truncated_json_is_rejected_not_repaired() -> None:
    raw = '{"instrument": "AAPL", "direction": "long", "confidence": 0.5'
    result = parse_proposal(raw)
    assert isinstance(result, RejectedProposal)
    assert result.reason == "schema_invalid"
    assert result.raw_output == raw


def test_direction_buy_is_rejected_not_mapped_to_long() -> None:
    raw = json.dumps(
        {
            "instrument": "AAPL",
            "direction": "buy",
            "confidence": 0.5,
            "rationale": "map me",
        }
    )
    result = parse_proposal(raw)
    assert isinstance(result, RejectedProposal)
    assert result.reason == "schema_invalid"


def test_confidence_out_of_range_is_not_clamped() -> None:
    raw = json.dumps(
        {
            "instrument": "AAPL",
            "direction": "long",
            "confidence": 1.4,
            "rationale": "clamp me",
        }
    )
    result = parse_proposal(raw)
    assert isinstance(result, RejectedProposal)
    assert "1.4" in result.raw_output


def test_think_blocks_stripped_then_valid_json_accepted() -> None:
    inner = json.dumps(
        {
            "instrument": "AAPL",
            "direction": "avoid",
            "confidence": 0.2,
            "rationale": "no edge",
        }
    )
    raw = f"<think>planning the trade</think>\n{inner}"
    assert "planning" not in strip_think_blocks(raw)
    result = parse_proposal(raw)
    assert isinstance(result, LLMProposal)
    assert result.direction == "avoid"


def test_out_of_universe_instrument_rejected() -> None:
    proposal = LLMProposal(
        instrument="FAKE",
        direction="long",
        confidence=0.9,
        rationale="not listed",
    )
    result = validate_against_universe(proposal, frozenset({"AAPL"}))
    assert isinstance(result, RejectedProposal)
    assert result.reason == "instrument_not_in_universe"


def test_in_universe_instrument_accepted() -> None:
    proposal = LLMProposal(
        instrument="AAPL",
        direction="exit",
        confidence=0.4,
        rationale="done",
    )
    result = validate_against_universe(proposal, frozenset({"AAPL", "MSFT"}))
    assert result is proposal


def test_load_universe_reads_repo_allowlist() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    symbols = load_universe(repo_root / "config" / "universe.yaml")
    assert "AAPL" in symbols
    assert "ETHUSD" in symbols


def test_load_universe_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing"):
        load_universe(tmp_path / "nope.yaml")


def test_generate_proposal_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    result = generate_proposal(
        ProposalInput(
            instrument="AAPL",
            as_of=datetime(2026, 9, 18, tzinfo=timezone.utc),
            market_summary="flat",
        ),
        ModelConfig(ollama_host="http://127.0.0.1:11434", model_name="qwen3:8b"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert isinstance(result, RejectedProposal)
    assert result.reason == "timeout"


def test_generate_proposal_model_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="ollama down")

    result = generate_proposal(
        ProposalInput(
            instrument="AAPL",
            as_of=datetime(2026, 9, 18, tzinfo=timezone.utc),
            market_summary="flat",
        ),
        ModelConfig(ollama_host="http://127.0.0.1:11434", model_name="qwen3:8b"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert isinstance(result, RejectedProposal)
    assert result.reason == "model_error"


def _draft_payload(**overrides: object) -> dict:
    body = {
        "asset": "ETHUSD",
        "timestamp": "2026-09-18T00:00:00+00:00",
        "timeframe": "1d",
        "analysis_type": "technical",
        "factual_summary": "EMA fast above slow.",
        "data_sources": [{"url": "kraken:ohlc", "as_of": "2026-09-18T00:00:00+00:00", "content_hash": "x"}],
        "bullish_case": "hold above slow",
        "bearish_case": "lose slow",
        "neutral_case": "range",
        "key_assumptions": ["spot"],
        "catalysts": ["unknown"],
        "risks": ["liquidity"],
        "invalidation_conditions": ["close below slow"],
        "confidence_score": 0.4,
        "uncertainty": "no funding",
        "recommended_action": "hold",
        "position_size_suggestion": None,
    }
    body.update(overrides)
    return body


def test_analysis_draft_rejects_numeric_size() -> None:
    raw = json.dumps(_draft_payload(position_size_suggestion=2.5))
    result = parse_analysis_draft(raw)
    assert isinstance(result, RejectedAnalysis)
    assert result.reason == "schema_invalid"


def test_analysis_draft_rejects_extra_size_field() -> None:
    raw = json.dumps(_draft_payload(position_size=99))
    result = parse_analysis_draft(raw)
    assert isinstance(result, RejectedAnalysis)


def test_generate_analysis_overwrites_governance_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = _draft_payload(required_human_approval=False, action_type="proposal_candidate")
        return httpx.Response(200, json={"message": {"content": json.dumps(body)}})

    result = generate_analysis(
        AnalysisInput(
            instrument="ETHUSD",
            as_of=datetime(2026, 9, 18, tzinfo=timezone.utc),
            analysis_type="technical",
            timeframe="1d",
            facts_bundle={"close": "2410", "funding": "unknown"},
        ),
        ModelConfig(ollama_host="http://127.0.0.1:11434", model_name="qwen3:8b"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert isinstance(result, LLMAnalysis)
    assert result.required_human_approval is True
    assert result.action_type == "research_only"
    assert result.position_size_suggestion is None
    assert result.audit_metadata.schema_version == "analysis.v1"


def test_generate_analysis_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    result = generate_analysis(
        AnalysisInput(
            instrument="ETHUSD",
            as_of=datetime(2026, 9, 18, tzinfo=timezone.utc),
            analysis_type="technical",
            timeframe="1d",
            facts_bundle={"close": "2410"},
        ),
        ModelConfig(ollama_host="http://127.0.0.1:11434", model_name="qwen3:8b"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert isinstance(result, RejectedAnalysis)
    assert result.reason == "timeout"
