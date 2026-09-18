"""Wiring engine <-> research: fail-open (research down => comportament neschimbat) și
injectare de context (research sus => ProposalContext.external_context populat)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.data.cache import canonical_dataset_hash
from src.data.sources import CsvBarDataSource
from src.engine.backtest_runner import run_backtest
from src.engine.cost_models import VenueCostConfig
from src.engine.proposal_types import ParsedProposal, ProposalContext, RejectedProposal
from src.engine.research_client import ResearchClient

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "bars_ethusd_1d.csv"


class _AlwaysLong:
    def request_proposal(
        self,
        context: ProposalContext,
        timeout_s: float | None = None,
    ) -> ParsedProposal | RejectedProposal:
        return ParsedProposal(
            instrument=context.instrument,
            direction="long",
            confidence=0.5,
            rationale="integration-stub",
        )


class _CapturingClient:
    def __init__(self) -> None:
        self.contexts: list[ProposalContext] = []

    def request_proposal(
        self,
        context: ProposalContext,
        timeout_s: float | None = None,
    ) -> ParsedProposal | RejectedProposal:
        self.contexts.append(context)
        return ParsedProposal(
            instrument=context.instrument,
            direction="long",
            confidence=0.5,
            rationale="integration-stub",
        )


def _bars():
    return CsvBarDataSource(FIXTURE).fetch_bars(
        "ETHUSD",
        datetime(2024, 11, 1, tzinfo=timezone.utc),
        datetime(2024, 12, 16, tzinfo=timezone.utc),
        "1d",
    )


def _run(tmp_path: Path, name: str, proposal_client, research_client=None):
    bars = _bars()
    return run_backtest(
        bars,
        universe_symbol="ETHUSD",
        timeframe="1d",
        strategy_kind="llm",
        costs=VenueCostConfig.for_multiplier(1),
        dataset_hash=canonical_dataset_hash(bars),
        halt_flag=tmp_path / f"halt-{name}.flag",
        proposal_client=proposal_client,
        research_client=research_client,
    )


def _down_research_client() -> ResearchClient:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("research process is down")

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:8766")
    return ResearchClient(base_url="http://127.0.0.1:8766", http_client=http)


def _up_research_client(context_text: str) -> ResearchClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "instrument": request.url.params["instrument"],
                "as_of": request.url.params["as_of"],
                "external_context": context_text,
                "sources": ["https://example.com/a"],
                "generated_at": request.url.params["as_of"],
                "document_count": 1,
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:8766")
    return ResearchClient(base_url="http://127.0.0.1:8766", http_client=http)


def test_no_research_client_behaves_as_baseline(tmp_path: Path) -> None:
    no_research = _run(tmp_path / "no-research", "no-research", _AlwaysLong())
    assert no_research.n_decisions > 0


def test_research_down_matches_no_research_client(tmp_path: Path) -> None:
    without = _run(tmp_path / "without", "without", _AlwaysLong(), research_client=None)
    with_down = _run(tmp_path / "down", "down", _AlwaysLong(), research_client=_down_research_client())
    assert without.comparable() == with_down.comparable()


def test_research_up_injects_external_context(tmp_path: Path) -> None:
    context_text = "EXTERNAL CONTEXT for ETHUSD as of ...\n\nSource 1: ..."
    capture = _CapturingClient()
    metrics = _run(
        tmp_path / "up",
        "up",
        capture,
        research_client=_up_research_client(context_text),
    )
    assert metrics.n_decisions > 0
    assert capture.contexts
    assert all(ctx.external_context == context_text for ctx in capture.contexts)


def test_research_client_never_crashes_on_bad_response(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:8766")
    broken = ResearchClient(base_url="http://127.0.0.1:8766", http_client=http)

    without = _run(tmp_path / "without2", "without2", _AlwaysLong(), research_client=None)
    with_broken = _run(tmp_path / "broken", "broken", _AlwaysLong(), research_client=broken)
    assert without.comparable() == with_broken.comparable()
