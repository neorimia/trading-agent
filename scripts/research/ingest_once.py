"""One-shot research ingest. Nu e daemon, nu pornește RSS, nu apelează /propose."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.research.ingest import (
    build_api_connector_from_env,
    ingest_active,
    load_cik_by_symbol,
    load_research_env,
    required_credentials,
)
from src.research.registry import load_source_registry
from src.research.store import MetadataStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One-shot ingest of reviewed research sources")
    parser.add_argument(
        "--registry",
        default=str(REPO_ROOT / "config" / "research_sources.yaml"),
    )
    parser.add_argument(
        "--cik-map",
        default=str(REPO_ROOT / "config" / "sec_cik.yaml"),
    )
    parser.add_argument(
        "--metadata-db",
        default="data/research/metadata.db",
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=7,
    )
    args = parser.parse_args(argv)

    load_research_env(env_path=REPO_ROOT / ".env.research")
    sources = load_source_registry(args.registry)
    required_credentials(sources)
    cik_by_symbol = load_cik_by_symbol(args.cik_map)
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=args.since_days)
    connector = build_api_connector_from_env(cik_by_symbol=cik_by_symbol)
    metadata = MetadataStore(args.metadata_db)
    try:
        written = ingest_active(
            sources,
            connector=connector,
            metadata=metadata,
            since=since,
            now=now,
        )
    finally:
        connector.close()
        metadata.close()
    print(f"ingested {written} documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
