"""One-shot research ingest. Nu e daemon, nu apelează /propose.

RSS: doar feed-ul oficial. API fără adapter e skip.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.research.ingest import (
    build_api_connector_from_env,
    build_rss_connector_from_env,
    ingest_active,
    load_cik_by_symbol,
    load_research_env,
    required_credentials,
)
from src.research.registry import load_source_registry
from src.research.repository import open_research_repository
from src.research.store import RawDocumentStore


def main(argv: list[str] | None = None) -> int:
    load_research_env(env_path=REPO_ROOT / ".env.research")
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
        default=os.environ.get("RESEARCH_METADATA_DB_PATH", "data/research/metadata.db"),
    )
    parser.add_argument(
        "--backend",
        choices=("sqlite", "postgres"),
        default=os.environ.get("RESEARCH_STORE_BACKEND", "sqlite"),
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("RESEARCH_DATABASE_URL"),
    )
    parser.add_argument(
        "--raw-document-dir",
        default=os.environ.get("RESEARCH_RAW_DOCUMENT_DIR", "data/research/raw"),
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=7,
    )
    args = parser.parse_args(argv)

    sources = load_source_registry(args.registry)
    required_credentials(sources)
    cik_by_symbol = load_cik_by_symbol(args.cik_map)
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=args.since_days)
    connector = build_api_connector_from_env(cik_by_symbol=cik_by_symbol)
    rss_connector = build_rss_connector_from_env()
    metadata = open_research_repository(
        backend=args.backend,
        sqlite_path=args.metadata_db,
        database_url=args.database_url,
    )
    raw_store = RawDocumentStore(args.raw_document_dir)
    try:
        written = ingest_active(
            sources,
            connector=connector,
            metadata=metadata,
            since=since,
            now=now,
            rss_connector=rss_connector,
            raw_store=raw_store,
        )
    finally:
        connector.close()
        rss_connector.close()
        metadata.close()
    print(f"ingested {written} documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
