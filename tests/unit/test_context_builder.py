"""R3 — build_external_context: funcție pură, determinist, fără rețea/LLM.

Cazuri cerute de checkpoint R3 (workflow_research-financiar.md §3, §7): gol, un document,
contradicție, staleness, multi-activ — fiecare verificat determinist.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.research.context_builder import FRED_ATTRIBUTION_DISCLAIMER, build_external_context
from src.research.models import ResearchDocument


def _document(
    *,
    doc_id: str = "doc-1",
    url: str = "https://example.com/a",
    source_id: str = "reuters-rss",
    published_at: datetime | None = datetime(2026, 9, 17, tzinfo=timezone.utc),
    event_date: datetime | None = None,
    fetched_at: datetime = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
    extracted_text: str = "The Federal Reserve held interest rates steady.",
    summary: str | None = None,
    sentiment_score: float | None = None,
    impact_magnitude: str | None = None,
    impact_direction: str | None = None,
    confidence_score: float = 0.8,
    last_verified_at: datetime = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
    content_hash: str = "hash-1",
) -> ResearchDocument:
    return ResearchDocument(
        doc_id=doc_id,
        url=url,
        title="Fed holds rates steady",
        source_id=source_id,
        author=None,
        published_at=published_at,
        fetched_at=fetched_at,
        event_date=event_date,
        assets_mentioned=["AAPL"],
        category="macro_indicator",
        extracted_text=extracted_text,
        summary=summary,
        sentiment_score=sentiment_score,
        impact_magnitude=impact_magnitude,
        impact_direction=impact_direction,
        confidence_score=confidence_score,
        last_verified_at=last_verified_at,
        content_hash=content_hash,
    )


AS_OF = datetime(2026, 9, 18, tzinfo=timezone.utc)


# --- gol ----------------------------------------------------------------------


def test_empty_documents_returns_explicit_no_coverage_message() -> None:
    text = build_external_context("AAPL", AS_OF, [])
    assert text == "No recent verified context available for AAPL."


# --- un document ----------------------------------------------------------------


def test_single_document_cites_source_url_and_timestamps() -> None:
    doc = _document()
    text = build_external_context("AAPL", AS_OF, [doc])
    assert "source=reuters-rss" in text
    assert "url=https://example.com/a" in text
    assert "published_at=2026-09-17T00:00:00+00:00" in text
    assert "event_date=unknown" in text
    assert "confidence_score=0.80" in text
    assert "Facts: The Federal Reserve held interest rates steady." in text
    assert "Interpretation: not yet analyzed" in text


def test_single_document_with_signal_fields_shows_interpretation() -> None:
    doc = _document(sentiment_score=-0.6, impact_magnitude="high", impact_direction="bearish")
    text = build_external_context("AAPL", AS_OF, [doc])
    assert "Interpretation: sentiment=-0.60, impact_magnitude=high, impact_direction=bearish" in text


# --- determinism ----------------------------------------------------------------


def test_same_documents_and_as_of_produce_identical_string() -> None:
    docs = [
        _document(doc_id="doc-1", content_hash="h1"),
        _document(doc_id="doc-2", content_hash="h2", url="https://example.com/b"),
    ]
    first = build_external_context("AAPL", AS_OF, docs)
    second = build_external_context("AAPL", AS_OF, list(docs))
    assert first == second


# --- contradicție ----------------------------------------------------------------


def test_contradicting_documents_both_appear_with_explicit_label() -> None:
    doc_a = _document(
        doc_id="doc-a",
        content_hash="h-a",
        url="https://reuters.example.com/a",
        source_id="reuters-rss",
        extracted_text="Fed signals rate cut is likely next quarter.",
    )
    doc_b = _document(
        doc_id="doc-b",
        content_hash="h-b",
        url="https://bloomberg.example.com/b",
        source_id="bloomberg-rss",
        extracted_text="Fed officials rule out a rate cut this year.",
    )
    text = build_external_context(
        "AAPL", AS_OF, [doc_a, doc_b], contradicting_pairs=[("doc-a", "doc-b")]
    )
    assert "Fed signals rate cut is likely next quarter." in text
    assert "Fed officials rule out a rate cut this year." in text
    assert "CONTRADICTING SOURCES:" in text
    assert "[reuters-rss] https://reuters.example.com/a vs [bloomberg-rss] https://bloomberg.example.com/b" in text
    assert "CONTRADICTS: doc-b" in text
    assert "CONTRADICTS: doc-a" in text


def test_contradicting_pair_referencing_document_outside_list_is_ignored() -> None:
    doc = _document(doc_id="doc-a", content_hash="h-a")
    text = build_external_context(
        "AAPL", AS_OF, [doc], contradicting_pairs=[("doc-a", "doc-not-in-list")]
    )
    assert "CONTRADICTING SOURCES:" not in text
    assert "CONTRADICTS" not in text


# --- staleness ----------------------------------------------------------------


def test_stale_context_gets_explicit_prefix() -> None:
    doc = _document(last_verified_at=datetime(2026, 9, 10, tzinfo=timezone.utc))
    text = build_external_context("AAPL", AS_OF, [doc])
    assert text.startswith("STALE CONTEXT — verify before use:")


def test_fresh_context_has_no_stale_prefix() -> None:
    doc = _document(last_verified_at=AS_OF - timedelta(hours=1))
    text = build_external_context("AAPL", AS_OF, [doc])
    assert not text.startswith("STALE CONTEXT")


def test_stale_after_threshold_is_configurable() -> None:
    doc = _document(last_verified_at=AS_OF - timedelta(hours=2))
    default_text = build_external_context("AAPL", AS_OF, [doc])
    tight_text = build_external_context(
        "AAPL", AS_OF, [doc], stale_after=timedelta(hours=1)
    )
    assert not default_text.startswith("STALE CONTEXT")
    assert tight_text.startswith("STALE CONTEXT")


# --- multi-activ ----------------------------------------------------------------


def test_multiple_instruments_produce_independent_deterministic_contexts() -> None:
    aapl_doc = _document(doc_id="doc-aapl", content_hash="h-aapl")
    eth_doc = _document(
        doc_id="doc-eth",
        content_hash="h-eth",
        url="https://example.com/eth",
        extracted_text="ETH network upgrade completed successfully.",
    )
    aapl_text_1 = build_external_context("AAPL", AS_OF, [aapl_doc])
    aapl_text_2 = build_external_context("AAPL", AS_OF, [aapl_doc])
    eth_text = build_external_context("ETHUSD", AS_OF, [eth_doc])

    assert aapl_text_1 == aapl_text_2
    assert aapl_text_1 != eth_text
    assert "EXTERNAL CONTEXT for AAPL" in aapl_text_1
    assert "EXTERNAL CONTEXT for ETHUSD" in eth_text
    assert "ETH network upgrade" in eth_text
    assert "ETH network upgrade" not in aapl_text_1


# --- validare as_of ----------------------------------------------------------------


def test_naive_as_of_raises_value_error() -> None:
    doc = _document()
    with pytest.raises(ValueError, match="timezone-aware"):
        build_external_context("AAPL", datetime(2026, 9, 18), [doc])


def test_fred_documents_append_required_attribution_disclaimer() -> None:
    doc = _document(source_id="fred", url="https://fred.stlouisfed.org/series/FEDFUNDS#2026-09-18")
    text = build_external_context("AAPL", AS_OF, [doc])
    assert text.endswith(FRED_ATTRIBUTION_DISCLAIMER)
    assert FRED_ATTRIBUTION_DISCLAIMER in text


def test_alfred_documents_append_required_attribution_disclaimer() -> None:
    doc = _document(source_id="alfred")
    text = build_external_context("AAPL", AS_OF, [doc])
    assert FRED_ATTRIBUTION_DISCLAIMER in text


def test_non_fred_documents_do_not_append_fred_disclaimer() -> None:
    doc = _document(source_id="reuters-rss")
    text = build_external_context("AAPL", AS_OF, [doc])
    assert FRED_ATTRIBUTION_DISCLAIMER not in text
