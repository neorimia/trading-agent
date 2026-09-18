"""R2 — extracție (boilerplate removal) + normalizare → ResearchDocument. Fără rețea."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.research.models import RawDocument
from src.research.store import extract_text, find_mentioned_assets, normalize_document

_ARTICLE_HTML = b"""
<html><head><title>Fed holds rates steady</title></head>
<body>
<nav>Home | Markets | About</nav>
<article>
<h1>Fed holds rates steady</h1>
<p>The Federal Reserve held interest rates steady on Wednesday, citing persistent
inflation concerns. Analysts expect AAPL and MSFT to see modest volatility as a result.</p>
</article>
<footer>Copyright 2026 - Terms of Service</footer>
</body></html>
"""


def _raw_document() -> RawDocument:
    return RawDocument(
        url="https://example.com/fed-article",
        source_id="reuters-rss",
        fetched_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        raw_payload_ref="ref-fed-article",
    )


# --- extract_text ------------------------------------------------------------


def test_extract_text_strips_nav_and_footer_boilerplate() -> None:
    text = extract_text(_ARTICLE_HTML, url="https://example.com/fed-article")
    assert "Federal Reserve held interest rates steady" in text
    assert "Home | Markets | About" not in text
    assert "Terms of Service" not in text


def test_extract_text_raises_on_empty_content() -> None:
    with pytest.raises(ValueError):
        extract_text(b"<html><body></body></html>", url="https://example.com/empty")


# --- find_mentioned_assets -----------------------------------------------------


def test_find_mentioned_assets_matches_whole_word_case_insensitive() -> None:
    text = "Analysts expect aapl and MSFT to see modest volatility."
    assert find_mentioned_assets(text, ["AAPL", "MSFT", "ETHUSD"]) == ["AAPL", "MSFT"]


def test_find_mentioned_assets_does_not_match_substring() -> None:
    text = "AAPLX is an unrelated ticker."
    assert find_mentioned_assets(text, ["AAPL"]) == []


# --- normalize_document --------------------------------------------------------


def test_normalize_document_produces_valid_research_document() -> None:
    raw = _raw_document()
    doc = normalize_document(
        raw,
        _ARTICLE_HTML,
        title="Fed holds rates steady",
        category="news",
        known_instruments=["AAPL", "MSFT", "ETHUSD"],
    )
    assert doc.source_id == "reuters-rss"
    assert doc.category == "news"
    assert doc.assets_mentioned == ["AAPL", "MSFT"]
    assert "Federal Reserve" in doc.extracted_text
    assert len(doc.content_hash) == 64
    assert len(doc.doc_id) == 64


def test_normalize_document_is_deterministic_for_same_input() -> None:
    raw = _raw_document()
    first = normalize_document(raw, _ARTICLE_HTML, title="t", category="news")
    second = normalize_document(raw, _ARTICLE_HTML, title="t", category="news")
    assert first.doc_id == second.doc_id
    assert first.content_hash == second.content_hash
