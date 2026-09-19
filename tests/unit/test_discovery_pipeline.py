"""Orchestrare end-to-end (fake provider, fără rețea) — funnel discover→filtre→scoring→rank."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.discovery.filters import load_filter_config
from src.discovery.models import DiscoveredInstrument, HistoricalStats, InstrumentSnapshot
from src.discovery.pipeline import run_discovery
from src.discovery.ranking import rank_candidates

_NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)


class FakeProvider:
    """Provider determinist: ETHUSD/BTCUSD lichide-valide, JUNKUSD eșuează pe lichiditate."""

    def __init__(self) -> None:
        # altname-style: ETHUSD/BTCUSD — trebuie să coincidă cu kraken_pair din venue_registry.py
        # pentru ca filtrul `has_execution_venue` să le recunoască drept deja executabile.
        self._instruments = [
            DiscoveredInstrument(exchange_pair="ETHUSD", base="XETH", quote="ZUSD", status="online"),
            DiscoveredInstrument(exchange_pair="BTCUSD", base="XXBT", quote="ZUSD", status="online"),
            DiscoveredInstrument(exchange_pair="JUNKUSD", base="JUNK", quote="ZUSD", status="online"),
        ]
        self._snapshots = {
            "ETHUSD": InstrumentSnapshot(exchange_pair="ETHUSD", last_price="2500", bid="2499", ask="2501", volume_24h="10000"),
            "BTCUSD": InstrumentSnapshot(exchange_pair="BTCUSD", last_price="60000", bid="59990", ask="60010", volume_24h="5000"),
            "JUNKUSD": InstrumentSnapshot(exchange_pair="JUNKUSD", last_price="0.01", bid="0.009", ask="0.011", volume_24h="10"),
        }

    def discover(self) -> list[DiscoveredInstrument]:
        return self._instruments

    def snapshot(self, exchange_pairs) -> dict[str, InstrumentSnapshot]:
        return {pair: self._snapshots[pair] for pair in exchange_pairs if pair in self._snapshots}

    def historical_stats(self, exchange_pair: str, *, history_days_requested: int = 90, now=None) -> HistoricalStats:
        base = {"ETHUSD": 2500.0, "BTCUSD": 60000.0, "JUNKUSD": 0.01}[exchange_pair]
        closes = [base * (1 + 0.001 * ((i % 5) - 2)) for i in range(history_days_requested)]
        volumes = [1000.0 + i for i in range(history_days_requested)]
        return HistoricalStats(
            exchange_pair=exchange_pair,
            listing_age_days=1000,
            history_days_available=history_days_requested,
            history_days_requested=history_days_requested,
            daily_closes=closes,
            daily_volumes=volumes,
        )


@pytest.fixture()
def filter_rules():
    return load_filter_config("config/discovery_filters.yaml")


def test_run_discovery_produces_candidates_for_liquid_instruments(filter_rules) -> None:
    run = run_discovery(FakeProvider(), filter_rules, now=_NOW)
    candidate_assets = {c.asset for c in run.candidates}
    assert "ETHUSD" in candidate_assets
    assert "BTCUSD" in candidate_assets


def test_run_discovery_rejects_illiquid_instrument_without_dropping_it(filter_rules) -> None:
    run = run_discovery(FakeProvider(), filter_rules, now=_NOW)
    rejected_assets = {r.asset for r in run.rejected}
    assert "JUNKUSD" in rejected_assets
    junk = next(r for r in run.rejected if r.asset == "JUNKUSD")
    assert junk.filter_results  # motivul nu dispare tăcut


def test_run_discovery_never_sets_requires_human_review_false(filter_rules) -> None:
    run = run_discovery(FakeProvider(), filter_rules, now=_NOW)
    assert all(c.requires_human_review is True for c in run.candidates)
    assert all(c.candidate_status == "research" for c in run.candidates)


def test_run_discovery_is_deterministic(filter_rules) -> None:
    run1 = run_discovery(FakeProvider(), filter_rules, now=_NOW)
    run2 = run_discovery(FakeProvider(), filter_rules, now=_NOW)
    scores1 = {c.asset: c.opportunity_score for c in run1.candidates}
    scores2 = {c.asset: c.opportunity_score for c in run2.candidates}
    assert scores1 == scores2


def test_rank_candidates_orders_by_composite_and_keeps_components(filter_rules) -> None:
    run = run_discovery(FakeProvider(), filter_rules, now=_NOW)
    ranked = rank_candidates(run.candidates)
    assert len(ranked) == len(run.candidates)
    ranks = [item.composite_rank for item in ranked]
    assert ranks == sorted(ranks, reverse=True)
    for item in ranked:
        assert item.candidate.opportunity_score is not None
        assert item.candidate.risk_score is not None
