"""Reproductibilitate: aceeași serie + același cache de propuneri → aceleași metrici."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.data.cache import canonical_dataset_hash
from src.data.sources import CsvBarDataSource
from src.engine.cost_models import VenueCostConfig
from src.engine.proposal_cache import CachingLLMProposalClient
from src.engine.proposal_types import ParsedProposal, ProposalContext, RejectedProposal
from src.engine.backtest_runner import run_backtest
from src.engine.signals import proposal_context_at

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


def _bars():
    return CsvBarDataSource(FIXTURE).fetch_bars(
        "ETHUSD",
        datetime(2024, 11, 1, tzinfo=timezone.utc),
        datetime(2024, 12, 16, tzinfo=timezone.utc),
        "1d",
    )


def _run(tmp_path: Path, kind: str, client=None):
    bars = _bars()
    return run_backtest(
        bars,
        universe_symbol="ETHUSD",
        timeframe="1d",
        strategy_kind=kind,
        costs=VenueCostConfig.for_multiplier(1),
        dataset_hash=canonical_dataset_hash(bars),
        halt_flag=tmp_path / f"halt-{kind}.flag",
        proposal_client=client,
    )


def test_baseline_repeated_run_identical(tmp_path: Path) -> None:
    first = _run(tmp_path / "a", "baseline")
    second = _run(tmp_path / "b", "baseline")
    assert first.comparable() == second.comparable()


def test_llm_strategy_repeated_run_identical_with_cache(tmp_path: Path) -> None:
    bars = _bars()
    cache_dir = tmp_path / "proposals"
    warmer = CachingLLMProposalClient(cache_dir, _AlwaysLong())
    for index in range(19, len(bars)):
        warmer.request_proposal(
            proposal_context_at(
                bars[: index + 1],
                fast_period=10,
                slow_period=20,
                lookback=20,
            )
        )
    frozen = CachingLLMProposalClient(cache_dir, inner=None, read_only=True)
    first = _run(tmp_path / "llm1", "llm", frozen)
    second = _run(tmp_path / "llm2", "llm", frozen)
    assert first.comparable() == second.comparable()
    assert first.n_decisions > 0
