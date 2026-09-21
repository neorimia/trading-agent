"""PostgreSQL research repository, constraints, concurrency, and import parity."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from scripts.db.import_research import import_research
from scripts.db.seed import seed_reference_data
from src.db.pool import close_database_pools
from src.research.models import ResearchDocument
from src.research.postgres_store import PostgresMetadataStore
from src.research.server import app
from src.research.store import MetadataStore

pytestmark = pytest.mark.postgres
REPO_ROOT = Path(__file__).resolve().parents[2]


def _database_url() -> str:
    """The research_writer application role, as production code paths use it."""
    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        pytest.skip("TEST_DATABASE_URL is not configured")
    return value


def _admin_database_url() -> str:
    """The migration-owner role, for schema setup/seeding outside app code paths."""
    value = os.environ.get("ADMIN_DATABASE_URL") or os.environ.get("MIGRATION_DATABASE_URL")
    if not value:
        pytest.skip("ADMIN_DATABASE_URL is not configured")
    return value


def _control_database_url() -> str:
    """The control_reader application role."""
    value = os.environ.get("CONTROL_DATABASE_URL")
    if not value:
        pytest.skip("CONTROL_DATABASE_URL is not configured")
    return value


@pytest.fixture(autouse=True)
def clean_database() -> None:
    url = _admin_database_url()
    close_database_pools()
    with psycopg.connect(url) as connection:
        connection.execute(
            """
            TRUNCATE
                research_analyses,
                document_relations,
                document_assets,
                research_document_occurrences,
                research_documents
            RESTART IDENTITY CASCADE
            """
        )
        seed_reference_data(
            connection,
            universe_path=REPO_ROOT / "config/universe.yaml",
            sources_path=REPO_ROOT / "config/research_sources.yaml",
        )
    yield
    close_database_pools()


def _document(
    doc_id: str = "doc-1",
    *,
    content_hash: str = "hash-1",
    assets: list[str] | None = None,
) -> ResearchDocument:
    moment = datetime(2026, 9, 18, tzinfo=timezone.utc)
    return ResearchDocument(
        doc_id=doc_id,
        url=f"https://example.test/{doc_id}",
        title="Research item",
        source_id="fred",
        fetched_at=moment,
        assets_mentioned=assets or ["AAPL"],
        category="macro_indicator",
        extracted_text="Canonical extracted text.",
        confidence_score=0.8,
        data_quality_score=0.9,
        last_verified_at=moment,
        content_hash=content_hash,
    )


def test_postgres_repository_matches_time_travel_and_dedup_contract() -> None:
    store = PostgresMetadataStore(_database_url())
    assert store.upsert(_document()) is True
    assert store.upsert(_document("doc-2", content_hash="hash-1")) is False

    results = store.query_for_context(
        "AAPL",
        datetime(2026, 9, 19, tzinfo=timezone.utc),
        limit=10,
    )
    assert [item.doc_id for item in results] == ["doc-1"]
    assert store.related_documents("doc-1") == [("doc-2", "duplicate_of")]


def test_postgres_constraints_reject_unknown_source() -> None:
    store = PostgresMetadataStore(_database_url())
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        store.upsert(_document().model_copy(update={"source_id": "unknown"}))


def test_postgres_research_service_readiness_and_context_cutover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    PostgresMetadataStore(_database_url()).upsert(_document())
    monkeypatch.setenv("RESEARCH_STORE_BACKEND", "postgres")
    monkeypatch.setenv("RESEARCH_DATABASE_URL", _database_url())
    with TestClient(app) as client:
        ready = client.get("/ready")
        context = client.get(
            "/context",
            params={
                "instrument": "AAPL",
                "as_of": "2026-09-19T00:00:00+00:00",
            },
        )
    assert ready.status_code == 200
    assert context.status_code == 200
    assert context.json()["document_count"] == 1


def test_concurrent_duplicate_upserts_create_one_canonical_document() -> None:
    def write(doc_id: str) -> bool:
        return PostgresMetadataStore(_database_url()).upsert(
            _document(doc_id, content_hash="shared")
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(write, ("doc-a", "doc-b")))
    assert sorted(outcomes) == [False, True]

    with psycopg.connect(_database_url()) as connection:
        assert connection.execute(
            "SELECT count(*) FROM research_documents WHERE content_hash = 'shared'"
        ).fetchone()[0] == 1
        assert connection.execute(
            """
            SELECT count(*) FROM research_document_occurrences
            WHERE occurrence_id IN ('doc-a', 'doc-b')
            """
        ).fetchone()[0] == 2


def test_control_reader_can_read_research_but_not_write() -> None:
    PostgresMetadataStore(_database_url()).upsert(_document())

    with psycopg.connect(_control_database_url()) as connection:
        count = connection.execute(
            "SELECT count(*) FROM research_documents WHERE doc_id = 'doc-1'"
        ).fetchone()[0]
        assert count == 1

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "UPDATE research_documents SET title = 'tampered' WHERE doc_id = 'doc-1'"
            )


def test_legacy_import_is_idempotent(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "metadata.db"
    legacy = MetadataStore(sqlite_path)
    legacy.upsert(_document())
    legacy.upsert(_document("doc-2", content_hash="hash-1"))
    legacy.close()

    kwargs = {
        "sqlite_path": sqlite_path,
        # The importer seeds reference data (exchanges/assets/instruments/sources)
        # in addition to research tables, so it must run as the migration owner,
        # exactly like the production cutover runbook.
        "database_url": _admin_database_url(),
        "universe_path": REPO_ROOT / "config/universe.yaml",
        "sources_path": REPO_ROOT / "config/research_sources.yaml",
        "dry_run": False,
    }
    first = import_research(**kwargs)
    second = import_research(**kwargs)
    assert first["destination"] == second["destination"]
    assert second["destination"]["documents"] == 1
    assert second["destination"]["occurrences"] == 2
    assert second["sample_content_hashes_missing"] == []
    with psycopg.connect(_database_url()) as connection:
        legacy_alias = connection.execute(
            """
            SELECT url, source_id, fetched_at, legacy_metadata_incomplete
            FROM research_document_occurrences
            WHERE occurrence_id = 'doc-2'
            """
        ).fetchone()
    assert legacy_alias == (None, None, None, True)
