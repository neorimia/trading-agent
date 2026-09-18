"""Server research: loopback only, GET /context orchestrează MetadataStore + context_builder."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.research.models import ResearchDocument
from src.research.server import app, validate_bind_host
from src.research.store import MetadataStore

AS_OF = datetime(2026, 9, 18, tzinfo=timezone.utc)


def _document(doc_id: str, content_hash: str, url: str = "https://example.com/a") -> ResearchDocument:
    return ResearchDocument(
        doc_id=doc_id,
        url=url,
        title="Fed holds rates steady",
        source_id="fred",
        author=None,
        published_at=datetime(2026, 9, 17, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
        event_date=None,
        assets_mentioned=["AAPL"],
        category="macro_indicator",
        extracted_text="The Federal Reserve held interest rates steady.",
        summary=None,
        sentiment_score=None,
        impact_magnitude=None,
        impact_direction=None,
        confidence_score=0.8,
        last_verified_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
        content_hash=content_hash,
    )


def test_validate_bind_host_accepts_loopback() -> None:
    assert validate_bind_host("127.0.0.1") == "127.0.0.1"
    assert validate_bind_host("localhost") == "localhost"
    assert validate_bind_host("::1") == "::1"


def test_validate_bind_host_rejects_wildcard() -> None:
    with pytest.raises(ValueError, match="loopback"):
        validate_bind_host("0.0.0.0")


def test_context_returns_200_with_documents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "metadata.db"
    store = MetadataStore(db_path)
    store.upsert(_document("doc-1", "hash-1"))
    store.close()
    monkeypatch.setenv("RESEARCH_METADATA_DB_PATH", str(db_path))

    with TestClient(app) as client:
        response = client.get("/context", params={"instrument": "AAPL", "as_of": AS_OF.isoformat()})

    assert response.status_code == 200
    body = response.json()
    assert body["instrument"] == "AAPL"
    assert body["document_count"] == 1
    assert body["sources"] == ["https://example.com/a"]
    assert "Federal Reserve held interest rates steady" in body["external_context"]


def test_context_returns_204_when_no_documents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "metadata.db"
    MetadataStore(db_path).close()
    monkeypatch.setenv("RESEARCH_METADATA_DB_PATH", str(db_path))

    with TestClient(app) as client:
        response = client.get("/context", params={"instrument": "AAPL", "as_of": AS_OF.isoformat()})

    assert response.status_code == 204


def test_context_rejects_extra_query_param(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "metadata.db"
    MetadataStore(db_path).close()
    monkeypatch.setenv("RESEARCH_METADATA_DB_PATH", str(db_path))

    with TestClient(app) as client:
        response = client.get(
            "/context",
            params={"instrument": "AAPL", "as_of": AS_OF.isoformat(), "inject_override": "true"},
        )

    assert response.status_code == 422


def test_context_marks_contradicting_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "metadata.db"
    store = MetadataStore(db_path)
    store.upsert(_document("doc-a", "hash-a", url="https://reuters.example.com/a"))
    store.upsert(_document("doc-b", "hash-b", url="https://bloomberg.example.com/b"))
    store._conn.execute(
        "INSERT INTO document_relations (doc_id, related_doc_id, relation_type) "
        "VALUES ('doc-a', 'doc-b', 'contradicts')"
    )
    store._conn.commit()
    store.close()
    monkeypatch.setenv("RESEARCH_METADATA_DB_PATH", str(db_path))

    with TestClient(app) as client:
        response = client.get("/context", params={"instrument": "AAPL", "as_of": AS_OF.isoformat()})

    assert response.status_code == 200
    assert "CONTRADICTING SOURCES:" in response.json()["external_context"]
