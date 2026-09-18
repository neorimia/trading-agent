"""Client HTTP engine: deserializează JSON brut fără tipuri din src.llm."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from src.engine.llm_client import LLMProposalClient
from src.engine.proposal_types import ParsedProposal, ProposalContext, RejectedProposal


def _context() -> ProposalContext:
    return ProposalContext(
        instrument="AAPL",
        as_of=datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc),
        market_summary="flat",
        external_context=None,
    )


def _client(handler) -> LLMProposalClient:
    http = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://127.0.0.1:8765",
    )
    return LLMProposalClient(
        base_url="http://127.0.0.1:8765",
        http_client=http,
    )


def test_request_proposal_parses_valid_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/propose"
        return httpx.Response(
            200,
            json={
                "instrument": "AAPL",
                "direction": "long",
                "confidence": 0.55,
                "rationale": "held support",
            },
        )

    result = _client(handler).request_proposal(_context())
    assert isinstance(result, ParsedProposal)
    assert type(result).__module__ == "src.engine.proposal_types"
    assert result.instrument == "AAPL"


def test_request_proposal_parses_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"reason": "schema_invalid", "raw_output": "nope"},
        )

    result = _client(handler).request_proposal(_context())
    assert isinstance(result, RejectedProposal)
    assert result.reason == "schema_invalid"


def test_request_proposal_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("late")

    result = _client(handler).request_proposal(_context(), timeout_s=1.0)
    assert isinstance(result, RejectedProposal)
    assert result.reason == "timeout"


def test_malformed_body_is_schema_invalid() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    result = _client(handler).request_proposal(_context())
    assert isinstance(result, RejectedProposal)
    assert result.reason == "schema_invalid"


def test_extra_fields_from_http_are_not_accepted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "instrument": "AAPL",
                "direction": "long",
                "confidence": 0.5,
                "rationale": "ok",
                "position_size": 99,
            },
        )

    result = _client(handler).request_proposal(_context())
    assert isinstance(result, RejectedProposal)
    assert result.reason == "schema_invalid"
