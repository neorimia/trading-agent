"""Faza 1 — discovery crypto-only pe Kraken: fără LLM, fără UI (design §10.9).

Output: JSON pe stdout (DiscoveryRun) + append în data/discovery/YYYY-MM-DD.jsonl.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.discovery.crypto.kraken_universe import KrakenAssetUniverseProvider
from src.discovery.filters import load_filter_config
from src.discovery.pipeline import run_discovery
from src.discovery.store import append_run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One-shot crypto asset discovery run (Kraken, Faza 1)")
    parser.add_argument("--filters", default=str(REPO_ROOT / "config" / "discovery_filters.yaml"))
    parser.add_argument("--history-days", type=int, default=90)
    parser.add_argument("--store-dir", default="data/discovery")
    args = parser.parse_args(argv)

    filter_rules = load_filter_config(args.filters)
    provider = KrakenAssetUniverseProvider()
    try:
        run = run_discovery(provider, filter_rules, history_days_requested=args.history_days)
    finally:
        provider.close()

    path = append_run(run, args.store_dir)
    print(json.dumps(json.loads(run.model_dump_json()), indent=2))
    print(f"\n{len(run.candidates)} candidates, {len(run.rejected)} rejected, appended to {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
