"""Client de propuneri + cache: hit-ul pe disc evită HTTP; extra=forbid e păstrat."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.engine.llm_client import LLMProposalClient
from src.engine.proposal_cache import CachingLLMProposalClient, context_cache_key
from src.engine.proposal_types import ParsedProposal, ProposalContext, RejectedProposal


def _context() -> ProposalContext:
    return ProposalContext(
        instrument="ETHUSD",
        as_of=datetime(2024, 11, 15, 23, 59, 59, tzinfo=timezone.utc),
        market_summary="close=2740 ema_fast>ema_slow",
        external_context=None,
    )


class _FixedClient:
    def __init__(self) -> None:
        self.calls = 0

    def request_proposal(
        self,
        context: ProposalContext,
        timeout_s: float | None = None,
    ) -> ParsedProposal | RejectedProposal:
        self.calls += 1
        return ParsedProposal(
            instrument=context.instrument,
            direction="long",
            confidence=0.4,
            rationale="cached-inner",
        )


def test_cache_key_is_stable_for_identical_context() -> None:
    assert context_cache_key(_context()) == context_cache_key(_context())


def test_cache_key_changes_when_summary_changes() -> None:
    other = ProposalContext(
        instrument="ETHUSD",
        as_of=datetime(2024, 11, 15, 23, 59, 59, tzinfo=timezone.utc),
        market_summary="different",
        external_context=None,
    )
    assert context_cache_key(_context()) != context_cache_key(other)


def test_second_call_does_not_hit_inner(tmp_path: Path) -> None:
    inner = _FixedClient()
    client = CachingLLMProposalClient(tmp_path, inner)
    first = client.request_proposal(_context())
    second = client.request_proposal(_context())
    assert inner.calls == 1
    assert first == second
    assert isinstance(second, ParsedProposal)
    assert second.rationale == "cached-inner"


def test_read_only_miss_is_rejected_not_fetched(tmp_path: Path) -> None:
    inner = _FixedClient()
    client = CachingLLMProposalClient(tmp_path, inner, read_only=True)
    result = client.request_proposal(_context())
    assert inner.calls == 0
    assert isinstance(result, RejectedProposal)
    assert result.reason == "model_error"


def test_http_inner_result_is_cached(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "instrument": "ETHUSD",
                "direction": "avoid",
                "confidence": 0.1,
                "rationale": "no edge",
            },
        )

    http = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://127.0.0.1:8765",
    )
    inner = LLMProposalClient(base_url="http://127.0.0.1:8765", http_client=http)
    client = CachingLLMProposalClient(tmp_path, inner)
    result = client.request_proposal(_context())
    replay = CachingLLMProposalClient(tmp_path, inner=None, read_only=True).request_proposal(
        _context()
    )
    assert isinstance(result, ParsedProposal)
    assert replay == result
