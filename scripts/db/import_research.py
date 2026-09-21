"""Import legacy research SQLite data into PostgreSQL idempotently."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.db.seed import seed_reference_data
from src.db.config import require_database_url
from src.db.pool import close_database_pools
from src.research.models import ResearchDocument
from src.research.postgres_store import PostgresMetadataStore


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _legacy_documents(connection: sqlite3.Connection) -> list[ResearchDocument]:
    connection.row_factory = sqlite3.Row
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(documents)").fetchall()
    }
    has_raw = "raw_payload_ref" in columns
    has_quality = "data_quality_score" in columns
    documents: list[ResearchDocument] = []
    for row in connection.execute("SELECT * FROM documents ORDER BY fetched_at, doc_id"):
        assets = [
            asset["instrument"]
            for asset in connection.execute(
                """
                SELECT instrument FROM document_assets
                WHERE doc_id = ? ORDER BY instrument
                """,
                (row["doc_id"],),
            ).fetchall()
        ]
        documents.append(
            ResearchDocument(
                doc_id=row["doc_id"],
                url=row["url"],
                title=row["title"],
                source_id=row["source_id"],
                author=row["author"],
                published_at=_parse_dt(row["published_at"]),
                fetched_at=_parse_dt(row["fetched_at"]),
                event_date=_parse_dt(row["event_date"]),
                assets_mentioned=assets,
                category=row["category"],
                extracted_text=row["extracted_text"],
                raw_payload_ref=row["raw_payload_ref"] if has_raw else None,
                summary=row["summary"],
                sentiment_score=row["sentiment_score"],
                impact_magnitude=row["impact_magnitude"],
                impact_direction=row["impact_direction"],
                confidence_score=row["confidence_score"],
                data_quality_score=row["data_quality_score"] if has_quality else None,
                last_verified_at=_parse_dt(row["last_verified_at"]),
                content_hash=row["content_hash"],
            )
        )
    return documents


def _legacy_relations(
    connection: sqlite3.Connection,
) -> list[tuple[str, str, str]]:
    connection.row_factory = sqlite3.Row
    return [
        (row["doc_id"], row["related_doc_id"], row["relation_type"])
        for row in connection.execute(
            """
            SELECT doc_id, related_doc_id, relation_type
            FROM document_relations
            ORDER BY doc_id, related_doc_id, relation_type
            """
        ).fetchall()
    ]


def import_research(
    *,
    sqlite_path: Path,
    database_url: str,
    universe_path: Path,
    sources_path: Path,
    dry_run: bool,
) -> dict[str, Any]:
    with sqlite3.connect(sqlite_path) as legacy:
        documents = _legacy_documents(legacy)
        relations = _legacy_relations(legacy)

    configured_sources = {
        doc.source_id for doc in documents
    }
    with psycopg.connect(database_url, row_factory=dict_row) as destination:
        if not dry_run:
            seed_reference_data(
                destination,
                universe_path=universe_path,
                sources_path=sources_path,
            )
        available_sources = {
            row["source_id"]
            for row in destination.execute("SELECT source_id FROM research_sources")
        }
        instruments = {
            row["canonical_symbol"]
            for row in destination.execute("SELECT canonical_symbol FROM instruments")
        }
    unresolved_sources = sorted(configured_sources - available_sources)
    if unresolved_sources:
        raise ValueError(f"unresolved research sources: {unresolved_sources}")

    unknown_instruments = sorted(
        {
            symbol
            for doc in documents
            for symbol in doc.assets_mentioned
            if symbol not in instruments
        }
    )
    raw_payload_missing = sum(doc.raw_payload_ref is None for doc in documents)
    duplicate_relations = [item for item in relations if item[2] == "duplicate_of"]
    canonical_ids = {doc.doc_id for doc in documents}
    semantic_relations = [
        item
        for item in relations
        if item[2] != "duplicate_of"
        and item[0] in canonical_ids
        and item[1] in canonical_ids
    ]

    if not dry_run:
        store = PostgresMetadataStore(database_url)
        try:
            for document in documents:
                mapped = document.model_copy(
                    update={
                        "assets_mentioned": [
                            symbol
                            for symbol in document.assets_mentioned
                            if symbol in instruments
                        ]
                    }
                )
                store.upsert(mapped)
        finally:
            store.close()

        by_id = {doc.doc_id: doc for doc in documents}
        with psycopg.connect(database_url, row_factory=dict_row) as destination:
            for canonical_id, duplicate_id, _ in duplicate_relations:
                canonical = by_id.get(canonical_id)
                if canonical is None:
                    raise ValueError(
                        f"duplicate relation references missing canonical {canonical_id!r}"
                    )
                destination.execute(
                    """
                    INSERT INTO research_document_occurrences (
                        occurrence_id, canonical_doc_id, url, source_id, fetched_at,
                        raw_payload_ref, legacy_metadata_incomplete
                    ) VALUES (%s, %s, NULL, NULL, NULL, NULL, true)
                    ON CONFLICT (occurrence_id) DO UPDATE SET
                        canonical_doc_id = EXCLUDED.canonical_doc_id,
                        legacy_metadata_incomplete = true
                    """,
                    (duplicate_id, canonical_id),
                )
            for doc_id, related_doc_id, relation_type in semantic_relations:
                destination.execute(
                    """
                    INSERT INTO document_relations (
                        doc_id, related_doc_id, relation_type
                    ) VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (doc_id, related_doc_id, relation_type),
                )
        close_database_pools()

    with psycopg.connect(database_url, row_factory=dict_row) as destination:
        destination_counts = {
            "documents": destination.execute(
                "SELECT count(*) AS count FROM research_documents"
            ).fetchone()["count"],
            "occurrences": destination.execute(
                "SELECT count(*) AS count FROM research_document_occurrences"
            ).fetchone()["count"],
            "assets": destination.execute(
                "SELECT count(*) AS count FROM document_assets"
            ).fetchone()["count"],
            "relations": destination.execute(
                "SELECT count(*) AS count FROM document_relations"
            ).fetchone()["count"],
        }
        missing_hashes = [
            doc.content_hash
            for doc in documents[:10]
            if destination.execute(
                "SELECT 1 FROM research_documents WHERE content_hash = %s",
                (doc.content_hash,),
            ).fetchone()
            is None
        ]

    return {
        "dry_run": dry_run,
        "legacy": {
            "documents": len(documents),
            "duplicate_occurrences": len(duplicate_relations),
            "semantic_relations": len(semantic_relations),
            "raw_payload_ref_missing": raw_payload_missing,
        },
        "destination": destination_counts,
        "unresolved_sources": unresolved_sources,
        "unknown_instruments": unknown_instruments,
        "sample_content_hashes_missing": missing_hashes,
        "idempotent_key": "doc_id/content_hash/occurrence_id",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=REPO_ROOT / "data/research/metadata.db",
    )
    parser.add_argument("--database-url", default=os.environ.get("MIGRATION_DATABASE_URL"))
    parser.add_argument("--universe", type=Path, default=REPO_ROOT / "config/universe.yaml")
    parser.add_argument(
        "--research-sources",
        type=Path,
        default=REPO_ROOT / "config/research_sources.yaml",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    if not args.sqlite.is_file():
        raise SystemExit(f"legacy SQLite database not found: {args.sqlite}")
    url = require_database_url(args.database_url, variable="MIGRATION_DATABASE_URL")
    report = import_research(
        sqlite_path=args.sqlite,
        database_url=url,
        universe_path=args.universe,
        sources_path=args.research_sources,
        dry_run=args.dry_run,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
