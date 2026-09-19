"""R2 — RawDocumentStore + MetadataStore: persistă, re-citește, filtrează pentru context."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.research.models import RawDocument, ResearchDocument
from src.research.store import MetadataStore, RawDocumentStore


def _raw_document(url: str = "https://example.com/a", ref: str = "ref-a") -> RawDocument:
    return RawDocument(
        url=url,
        source_id="fred",
        fetched_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        raw_payload_ref=ref,
    )


def _research_document(
    *,
    doc_id: str = "doc-1",
    content_hash: str = "hash-1",
    assets_mentioned: list[str] | None = None,
    fetched_at: datetime = datetime(2026, 9, 18, tzinfo=timezone.utc),
    published_at: datetime | None = None,
    category: str = "macro_indicator",
) -> ResearchDocument:
    return ResearchDocument(
        doc_id=doc_id,
        url="https://example.com/a",
        title="Fed holds rates steady",
        source_id="fred",
        author=None,
        published_at=published_at,
        fetched_at=fetched_at,
        event_date=None,
        assets_mentioned=assets_mentioned or [],
        category=category,  # type: ignore[arg-type]
        extracted_text="The Federal Reserve held interest rates steady.",
        summary=None,
        sentiment_score=None,
        impact_magnitude=None,
        impact_direction=None,
        confidence_score=0.5,
        last_verified_at=fetched_at,
        content_hash=content_hash,
    )


# --- RawDocumentStore -------------------------------------------------------


def test_raw_document_store_round_trip(tmp_path: Path) -> None:
    store = RawDocumentStore(tmp_path / "raw_documents")
    doc = _raw_document()
    ref = store.save(doc, b"<html>hello</html>")
    assert ref == doc.raw_payload_ref
    assert store.load(ref) == b"<html>hello</html>"


def test_raw_document_store_is_immutable_on_rewrite(tmp_path: Path) -> None:
    store = RawDocumentStore(tmp_path / "raw_documents")
    doc = _raw_document()
    store.save(doc, b"first payload")
    store.save(doc, b"second payload -- should be ignored")
    assert store.load(doc.raw_payload_ref) == b"first payload"


def test_raw_document_store_load_missing_ref_raises(tmp_path: Path) -> None:
    store = RawDocumentStore(tmp_path / "raw_documents")
    try:
        store.load("does-not-exist")
        assert False, "expected ValueError"
    except ValueError:
        pass


# --- MetadataStore: upsert + read back --------------------------------------


def test_upsert_new_document_returns_true_and_round_trips(tmp_path: Path) -> None:
    metadata = MetadataStore(tmp_path / "metadata.db")
    doc = _research_document(assets_mentioned=["AAPL", "MSFT"])
    assert metadata.upsert(doc) is True
    fetched = metadata.find_by_content_hash(doc.content_hash)
    assert fetched is not None
    assert fetched.doc_id == doc.doc_id
    assert fetched.assets_mentioned == ["AAPL", "MSFT"]
    assert fetched.fetched_at == doc.fetched_at


def test_upsert_same_doc_id_again_replaces_row(tmp_path: Path) -> None:
    metadata = MetadataStore(tmp_path / "metadata.db")
    doc = _research_document()
    metadata.upsert(doc)
    updated = doc.model_copy(update={"summary": "revised summary"})
    assert metadata.upsert(updated) is True
    fetched = metadata.find_by_content_hash(doc.content_hash)
    assert fetched is not None
    assert fetched.summary == "revised summary"


def test_find_by_content_hash_missing_returns_none(tmp_path: Path) -> None:
    metadata = MetadataStore(tmp_path / "metadata.db")
    assert metadata.find_by_content_hash("no-such-hash") is None


# --- MetadataStore: query_for_context ---------------------------------------


def test_query_for_context_filters_by_instrument_and_as_of(tmp_path: Path) -> None:
    metadata = MetadataStore(tmp_path / "metadata.db")
    older = _research_document(
        doc_id="doc-old",
        content_hash="hash-old",
        assets_mentioned=["AAPL"],
        fetched_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
    )
    newer = _research_document(
        doc_id="doc-new",
        content_hash="hash-new",
        assets_mentioned=["AAPL"],
        fetched_at=datetime(2026, 9, 17, tzinfo=timezone.utc),
    )
    other_asset = _research_document(
        doc_id="doc-other",
        content_hash="hash-other",
        assets_mentioned=["MSFT"],
        fetched_at=datetime(2026, 9, 17, tzinfo=timezone.utc),
    )
    future = _research_document(
        doc_id="doc-future",
        content_hash="hash-future",
        assets_mentioned=["AAPL"],
        fetched_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
    )
    for doc in (older, newer, other_asset, future):
        metadata.upsert(doc)

    as_of = datetime(2026, 9, 18, tzinfo=timezone.utc)
    results = metadata.query_for_context("AAPL", as_of, limit=5)

    assert [doc.doc_id for doc in results] == ["doc-new", "doc-old"]


def test_query_for_context_respects_limit(tmp_path: Path) -> None:
    metadata = MetadataStore(tmp_path / "metadata.db")
    for i in range(3):
        metadata.upsert(
            _research_document(
                doc_id=f"doc-{i}",
                content_hash=f"hash-{i}",
                assets_mentioned=["AAPL"],
                fetched_at=datetime(2026, 9, 10 + i, tzinfo=timezone.utc),
            )
        )
    as_of = datetime(2026, 9, 18, tzinfo=timezone.utc)
    results = metadata.query_for_context("AAPL", as_of, limit=1)
    assert len(results) == 1
    assert results[0].doc_id == "doc-2"


def test_query_for_context_excludes_future_published_at(tmp_path: Path) -> None:
    metadata = MetadataStore(tmp_path / "metadata.db")
    as_of = datetime(2026, 9, 18, tzinfo=timezone.utc)
    known = _research_document(
        doc_id="doc-known",
        content_hash="hash-known",
        assets_mentioned=["ETHUSD"],
        fetched_at=datetime(2026, 9, 17, tzinfo=timezone.utc),
        published_at=datetime(2026, 9, 17, tzinfo=timezone.utc),
        category="protocol_upgrade",
    )
    leaked = _research_document(
        doc_id="doc-leaked",
        content_hash="hash-leaked",
        assets_mentioned=["ETHUSD"],
        fetched_at=datetime(2026, 9, 17, tzinfo=timezone.utc),
        published_at=datetime(2026, 9, 19, tzinfo=timezone.utc),
        category="token_unlock",
    )
    metadata.upsert(known)
    metadata.upsert(leaked)
    results = metadata.query_for_context("ETHUSD", as_of, limit=10)
    assert [doc.doc_id for doc in results] == ["doc-known"]
