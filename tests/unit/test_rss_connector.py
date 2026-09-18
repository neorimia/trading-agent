"""R1a — RssConnector: parsare feed → RawDocument, zero rețea în CI (fixture local via MockTransport)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from src.research.connectors import RssConnector
from src.research.models import RawDocument, SourceConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "research_rss_sample.xml"


def _source(**overrides: object) -> SourceConfig:
    payload = {
        "source_id": "sample_press",
        "name": "Sample Financial Press",
        "kind": "rss",
        "base_url": "https://example-press.test/feed.xml",
        "credibility_score": 0.7,
        "robots_txt_status": "allowed",
        "tos_reviewed_at": datetime(2026, 9, 18, tzinfo=timezone.utc),
        "rate_limit_per_min": None,
    }
    payload.update(overrides)
    return SourceConfig.model_validate(payload)


def _client_for_fixture() -> httpx.Client:
    body = FIXTURE.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": "application/rss+xml"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_returns_raw_documents_from_local_fixture() -> None:
    connector = RssConnector(http_client=_client_for_fixture())
    since = datetime(2026, 9, 16, tzinfo=timezone.utc)
    now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)

    documents = connector.fetch(_source(), since, now=now)

    assert documents
    assert all(isinstance(doc, RawDocument) for doc in documents)
    assert all(doc.source_id == "sample_press" for doc in documents)
    assert all(doc.fetched_at == now for doc in documents)
    assert all(doc.raw_payload_ref for doc in documents)


def test_fetch_filters_entries_older_than_since() -> None:
    connector = RssConnector(http_client=_client_for_fixture())
    since = datetime(2026, 9, 16, tzinfo=timezone.utc)

    documents = connector.fetch(_source(), since)

    urls = {doc.url for doc in documents}
    assert "https://example-press.test/articles/old-news" not in urls
    assert "https://example-press.test/articles/fresh-macro-update" in urls
    assert "https://example-press.test/articles/latest-earnings-commentary" in urls


def test_fetch_includes_entries_with_no_pubdate() -> None:
    connector = RssConnector(http_client=_client_for_fixture())
    since = datetime(2026, 9, 16, tzinfo=timezone.utc)

    documents = connector.fetch(_source(), since)

    urls = {doc.url for doc in documents}
    assert "https://example-press.test/articles/undated-wire-item" in urls


def test_fetch_rejects_non_rss_source() -> None:
    connector = RssConnector(http_client=_client_for_fixture())
    with pytest.raises(ValueError, match="cannot fetch source kind"):
        connector.fetch(_source(kind="api"), datetime(2026, 9, 16, tzinfo=timezone.utc))


def test_fetch_raw_payload_ref_is_deterministic() -> None:
    connector = RssConnector(http_client=_client_for_fixture())
    since = datetime(2026, 9, 16, tzinfo=timezone.utc)
    now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)

    first = connector.fetch(_source(), since, now=now)
    second = connector.fetch(_source(), since, now=now)

    assert [doc.raw_payload_ref for doc in first] == [doc.raw_payload_ref for doc in second]


def test_fetch_makes_no_real_network_call() -> None:
    """Le transport e un MockTransport local — orice tentativă de rețea reală ar eșua imediat."""
    connector = RssConnector(http_client=_client_for_fixture())
    documents = connector.fetch(_source(), datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert len(documents) == 4
