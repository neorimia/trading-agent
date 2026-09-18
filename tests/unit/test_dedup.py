"""R2 — deduplicare pe content_hash (checkpoint R2, workflow_research-financiar.md §3).

Ingestia aceluiași conținut de 2 ori trebuie să producă un singur rând în `documents`;
al doilea document apare doar ca `duplicate_of` în `document_relations`, nu dispare silențios.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.research.models import ResearchDocument
from src.research.store import MetadataStore, compute_content_hash


def _document(doc_id: str, url: str, content_hash: str) -> ResearchDocument:
    return ResearchDocument(
        doc_id=doc_id,
        url=url,
        title="Fed holds rates steady",
        source_id="fred",
        author=None,
        published_at=None,
        fetched_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        event_date=None,
        assets_mentioned=["AAPL"],
        category="macro_indicator",
        extracted_text="The Federal Reserve held interest rates steady.",
        summary=None,
        sentiment_score=None,
        impact_magnitude=None,
        impact_direction=None,
        confidence_score=0.5,
        last_verified_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        content_hash=content_hash,
    )


def test_ingesting_same_content_twice_keeps_one_row_and_links_duplicate(tmp_path: Path) -> None:
    metadata = MetadataStore(tmp_path / "metadata.db")
    shared_hash = compute_content_hash("The Federal Reserve held interest rates steady.")

    first = _document("doc-1", "https://reuters.example.com/fed-article", shared_hash)
    second = _document("doc-2", "https://yahoo.example.com/fed-article-mirror", shared_hash)

    assert metadata.upsert(first) is True
    assert metadata.upsert(second) is False

    assert metadata.find_by_content_hash(shared_hash).doc_id == "doc-1"

    relations = metadata.related_documents("doc-1")
    assert relations == [("doc-2", "duplicate_of")]

    # doc-2 nu are propriul rând în documents — query_for_context nu poate sub doc-2 direct.
    fetched_via_context = metadata.query_for_context("AAPL", datetime(2026, 9, 19, tzinfo=timezone.utc), limit=10)
    assert [doc.doc_id for doc in fetched_via_context] == ["doc-1"]


def test_content_hash_unique_constraint_holds_for_direct_sql_collision(tmp_path: Path) -> None:
    """Testul explicit de coliziune cerut de workflow §3 — insert SQL brut cu content_hash duplicat eșuează."""
    metadata = MetadataStore(tmp_path / "metadata.db")
    metadata.upsert(_document("doc-1", "https://example.com/a", "shared-hash"))
    try:
        metadata._conn.execute(
            """
            INSERT INTO documents (
                doc_id, url, title, source_id, fetched_at, category,
                extracted_text, confidence_score, last_verified_at, content_hash
            ) VALUES ('doc-2', 'https://example.com/b', 't', 'fred',
                      '2026-09-18T00:00:00+00:00', 'macro_indicator', 'text', 0.5,
                      '2026-09-18T00:00:00+00:00', 'shared-hash')
            """
        )
        assert False, "expected sqlite3.IntegrityError on duplicate content_hash"
    except Exception as exc:
        assert "UNIQUE" in str(exc)


def test_compute_content_hash_ignores_whitespace_and_case_differences() -> None:
    a = compute_content_hash("Fed   holds  rates STEADY.")
    b = compute_content_hash("fed holds rates steady.")
    assert a == b


def test_compute_content_hash_differs_for_different_text() -> None:
    a = compute_content_hash("Fed holds rates steady.")
    b = compute_content_hash("Fed cuts rates by 25bps.")
    assert a != b
