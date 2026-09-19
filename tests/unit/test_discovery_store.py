"""Persistență JSONL append-only pentru discovery (design §5, §6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.discovery.models import AssetCandidate, CandidateFactors, DiscoveryRun, SourceRef
from src.discovery.store import append_run, load_day

_NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def _candidate(asset: str) -> AssetCandidate:
    return AssetCandidate(
        asset=asset,
        asset_class="crypto",
        exchange="KRAKEN",
        timestamp=_NOW,
        research_horizon="swing (days-weeks)",
        candidate_status="research",
        opportunity_score=0.5,
        risk_score=0.3,
        confidence_score=0.6,
        data_quality_score=1.0,
        factors=CandidateFactors(
            notional_volume_24h_usd="1000000",
            spread_bps=5.0,
            liquidity_score=0.5,
            spread_score=0.5,
            data_quality_score=1.0,
            operational_risk_score=0.1,
            listing_age_days=100,
            exchange_status="online",
        ),
        sources=[SourceRef(source_id="kraken_public_api", url="https://api.kraken.com/0/public", fetched_at=_NOW)],
        expires_at=_NOW + timedelta(hours=24),
    )


def test_append_run_writes_one_line_per_candidate(tmp_path) -> None:
    run = DiscoveryRun(run_at=_NOW, exchange="KRAKEN", candidates=[_candidate("ETHUSD"), _candidate("BTCUSD")], rejected=[])
    path = append_run(run, tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert path.name == "2026-09-20.jsonl"


def test_append_run_appends_across_multiple_calls(tmp_path) -> None:
    run1 = DiscoveryRun(run_at=_NOW, exchange="KRAKEN", candidates=[_candidate("ETHUSD")], rejected=[])
    run2 = DiscoveryRun(run_at=_NOW, exchange="KRAKEN", candidates=[_candidate("BTCUSD")], rejected=[])
    append_run(run1, tmp_path)
    append_run(run2, tmp_path)
    loaded = load_day(tmp_path, "2026-09-20")
    assert {c.asset for c in loaded} == {"ETHUSD", "BTCUSD"}


def test_load_day_missing_file_returns_empty_list(tmp_path) -> None:
    assert load_day(tmp_path, "1999-01-01") == []
