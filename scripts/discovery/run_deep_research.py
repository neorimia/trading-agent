"""Faza 2 — narativ LLM pentru top-N candidați deja descoperiți (design §6, §10.9).

Singurul job care apelează LLM-ul pentru discovery (§6). Nu recalculează scoruri —
citește candidați deja persistați de `run_daily_discovery.py`, cere un narativ pentru
cei mai bine clasați, și îi re-adaugă (append-only, §7) în același store.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.discovery.llm_summary import summarize_candidate
from src.discovery.models import AssetCandidate, DiscoveryRun
from src.discovery.ranking import rank_candidates
from src.discovery.store import append_run, load_day
from src.engine.analysis_client import LLMAnalysisClient


def _latest_day_candidates(
    store_dir: str, *, now: datetime, lookback_days: int
) -> list[AssetCandidate]:
    """Ultima zi cu date, dedus pe `asset` cu `timestamp` maxim (mirror runtime_state.py)."""
    for offset in range(lookback_days + 1):
        day = (now - timedelta(days=offset)).strftime("%Y-%m-%d")
        candidates = load_day(store_dir, day)
        if not candidates:
            continue
        latest_by_asset: dict[str, AssetCandidate] = {}
        for candidate in candidates:
            current = latest_by_asset.get(candidate.asset)
            if current is None or candidate.timestamp > current.timestamp:
                latest_by_asset[candidate.asset] = candidate
        return list(latest_by_asset.values())
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate LLM narrative summaries for the top-N discovery candidates (Faza 2)"
    )
    parser.add_argument("--store-dir", default="data/discovery")
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--lookback-days", type=int, default=3)
    parser.add_argument("--llm-url", default="http://127.0.0.1:8765")
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    candidates = _latest_day_candidates(args.store_dir, now=now, lookback_days=args.lookback_days)
    if not candidates:
        print("no discovery candidates found", file=sys.stderr)
        return 0

    ranked = rank_candidates(candidates)[: args.top_n]

    client = LLMAnalysisClient(args.llm_url)
    try:
        updated = [
            summarize_candidate(item.candidate, client.request_analysis, now=now) for item in ranked
        ]
    finally:
        client.close()

    by_exchange: dict[str, list[AssetCandidate]] = defaultdict(list)
    for candidate in updated:
        by_exchange[candidate.exchange].append(candidate)

    for exchange, group in by_exchange.items():
        path = append_run(
            DiscoveryRun(run_at=now, exchange=exchange, candidates=group, rejected=[]),
            args.store_dir,
        )
        print(f"{len(group)} {exchange} candidates summarized, appended to {path}", file=sys.stderr)

    print(json.dumps([json.loads(c.model_dump_json()) for c in updated], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
