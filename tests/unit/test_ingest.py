"""One-shot ingest: doar active_sources, pending → ValueError fără HTTP."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from src.research.connectors import ApiConnector, RssConnector
from src.research.ingest import ingest_active, ingest_source, required_credentials
from src.research.models import SourceConfig
from src.research.store import MetadataStore

REPO_ROOT = Path(__file__).resolve().parents[2]
RSS_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "research_rss_sample.xml"


def _fred_source(**overrides: object) -> SourceConfig:
    payload = {
        "source_id": "fred",
        "name": "FRED",
        "kind": "api",
        "base_url": "https://api.stlouisfed.org/fred",
        "credibility_score": 0.95,
        "robots_txt_status": "not_applicable_api",
        "tos_reviewed_at": datetime(2026, 9, 18, tzinfo=timezone.utc),
        "rate_limit_per_min": 120,
        "review_status": "reviewed",
    }
    payload.update(overrides)
    return SourceConfig.model_validate(payload)


def _rss_pending() -> SourceConfig:
    return SourceConfig.model_validate(
        {
            "source_id": "sec_press_rss",
            "name": "SEC Press",
            "kind": "rss",
            "base_url": "https://www.sec.gov/news/pressreleases.rss",
            "credibility_score": 0.98,
            "robots_txt_status": "pending",
            "tos_reviewed_at": None,
            "review_status": "pending_manual_tos_review",
        }
    )


def _rss_reviewed() -> SourceConfig:
    return _rss_pending().model_copy(
        update={
            "review_status": "reviewed",
            "tos_reviewed_at": datetime(2026, 9, 18, tzinfo=timezone.utc),
            "robots_txt_status": "allowed",
            "base_url": "https://example-press.test/feed.xml",
            "source_id": "sample_press",
            "name": "Sample Financial Press",
        }
    )


def _ecb_reviewed() -> SourceConfig:
    return SourceConfig.model_validate(
        {
            "source_id": "ecb_data",
            "name": "ECB Data Portal",
            "kind": "api",
            "base_url": "https://data-api.ecb.europa.eu/service",
            "credibility_score": 0.98,
            "robots_txt_status": "not_applicable_api",
            "tos_reviewed_at": datetime(2026, 9, 19, tzinfo=timezone.utc),
            "review_status": "reviewed",
        }
    )


def _client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ingest_pending_source_raises_without_http(tmp_path: Path) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"observations": []})

    connector = ApiConnector(http_client=_client_for(handler), api_key="test-key")
    metadata = MetadataStore(tmp_path / "metadata.db")
    pending = _fred_source(review_status="pending", tos_reviewed_at=None)
    with pytest.raises(ValueError, match="not fetchable"):
        ingest_source(
            pending,
            connector=connector,
            metadata=metadata,
            since=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
    assert captured == []
    assert metadata.list_documents() == []


def test_ingest_active_skips_pending_rss_without_http(tmp_path: Path) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={"observations": [{"date": "2026-09-18", "value": "5.35"}]},
        )

    connector = ApiConnector(
        http_client=_client_for(handler), api_key="test-key", sleep_fn=lambda _: None
    )
    metadata = MetadataStore(tmp_path / "metadata.db")
    written = ingest_active(
        [_rss_pending(), _fred_source()],
        connector=connector,
        metadata=metadata,
        since=datetime(2026, 9, 1, tzinfo=timezone.utc),
        now=datetime(2026, 9, 18, tzinfo=timezone.utc),
    )
    assert written > 0
    assert captured
    assert all(req.url.host == "api.stlouisfed.org" for req in captured)
    stored = metadata.list_documents()
    assert stored
    assert all(doc.source_id == "fred" for doc in stored)


def test_required_credentials_fail_loud_when_fred_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(ValueError, match="FRED_API_KEY"):
        required_credentials([_fred_source()])


def test_ingest_reviewed_rss_writes_feed_items_without_article_http(tmp_path: Path) -> None:
    captured: list[httpx.Request] = []
    body = RSS_FIXTURE.read_bytes()

    def rss_handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200, content=body, headers={"content-type": "application/rss+xml"}
        )

    api_captured: list[httpx.Request] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        api_captured.append(request)
        return httpx.Response(200, json={"observations": []})

    rss = RssConnector(http_client=_client_for(rss_handler))
    connector = ApiConnector(http_client=_client_for(api_handler), api_key="test-key")
    metadata = MetadataStore(tmp_path / "metadata.db")
    written = ingest_source(
        _rss_reviewed(),
        connector=connector,
        metadata=metadata,
        rss_connector=rss,
        since=datetime(2026, 9, 16, tzinfo=timezone.utc),
        now=datetime(2026, 9, 18, tzinfo=timezone.utc),
    )
    assert written > 0
    assert api_captured == []
    assert captured
    assert all(req.url.host == "example-press.test" for req in captured)
    assert all(req.url.path == "/feed.xml" for req in captured)
    stored = metadata.list_documents()
    assert stored
    assert all(doc.source_id == "sample_press" for doc in stored)
    assert all(doc.category == "news" for doc in stored)
    titles = {doc.title for doc in stored}
    assert "Fresh macro update" in titles


def test_ingest_pending_rss_raises_without_http(tmp_path: Path) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, content=b"")

    rss = RssConnector(http_client=_client_for(handler))
    connector = ApiConnector(http_client=_client_for(handler), api_key="test-key")
    metadata = MetadataStore(tmp_path / "metadata.db")
    with pytest.raises(ValueError, match="not fetchable"):
        ingest_source(
            _rss_pending(),
            connector=connector,
            metadata=metadata,
            rss_connector=rss,
            since=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
    assert captured == []


def test_ingest_unknown_api_is_skipped_without_http(tmp_path: Path) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    connector = ApiConnector(http_client=_client_for(handler), api_key="test-key")
    metadata = MetadataStore(tmp_path / "metadata.db")
    written = ingest_source(
        _ecb_reviewed(),
        connector=connector,
        metadata=metadata,
        since=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    assert written == 0
    assert captured == []
    assert metadata.list_documents() == []
