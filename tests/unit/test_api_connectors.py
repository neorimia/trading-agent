"""R1b — ApiConnector (FRED, SEC EDGAR): mock HTTP, rate limit explicit testabil, zero rețea reală."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from src.research.connectors import ApiConnector
from src.research.models import RawDocument, SourceConfig


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
    }
    payload.update(overrides)
    return SourceConfig.model_validate(payload)


def _sec_edgar_source(**overrides: object) -> SourceConfig:
    payload = {
        "source_id": "sec_edgar",
        "name": "SEC EDGAR",
        "kind": "api",
        "base_url": "https://data.sec.gov",
        "credibility_score": 0.98,
        "robots_txt_status": "not_applicable_api",
        "tos_reviewed_at": datetime(2026, 9, 18, tzinfo=timezone.utc),
        "rate_limit_per_min": 600,
    }
    payload.update(overrides)
    return SourceConfig.model_validate(payload)


def _client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _fred_observations_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "observations": [
                {"date": "2026-09-10", "value": "."},
                {"date": "2026-09-17", "value": "5.33"},
                {"date": "2026-09-18", "value": "5.35"},
            ]
        },
    )


def test_fred_fetch_returns_raw_documents_for_new_observations() -> None:
    connector = ApiConnector(
        http_client=_client_for(_fred_observations_response),
        api_key="test-key",
        sleep_fn=lambda _: None,
    )
    since = datetime(2026, 9, 16, tzinfo=timezone.utc)
    now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)

    documents = connector.fetch(_fred_source(), since, now=now)

    assert documents
    assert all(isinstance(doc, RawDocument) for doc in documents)
    assert all(doc.source_id == "fred" for doc in documents)
    assert all(doc.fetched_at == now for doc in documents)
    # 3 series (FEDFUNDS, CPIAUCSL, UNRATE) x 2 valid new observations each = 6.
    assert len(documents) == 6


def test_fred_fetch_skips_dot_placeholder_and_stale_observations() -> None:
    connector = ApiConnector(
        http_client=_client_for(_fred_observations_response),
        api_key="test-key",
        sleep_fn=lambda _: None,
    )
    since = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)

    documents = connector.fetch(_fred_source(), since)

    dates = {doc.url.split("#")[-1] for doc in documents}
    assert "2026-09-10" not in dates
    assert "2026-09-17" not in dates
    assert "2026-09-18" in dates


def test_fred_fetch_requires_api_key() -> None:
    connector = ApiConnector(http_client=_client_for(_fred_observations_response))
    with pytest.raises(ValueError, match="api_key"):
        connector.fetch(_fred_source(), datetime(2026, 9, 16, tzinfo=timezone.utc))


def test_fred_fetch_sends_api_key_and_no_real_network_call() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _fred_observations_response(request)

    connector = ApiConnector(
        http_client=_client_for(handler), api_key="secret-key", sleep_fn=lambda _: None
    )
    connector.fetch(_fred_source(), datetime(2026, 9, 16, tzinfo=timezone.utc))

    assert captured
    assert all(req.url.params["api_key"] == "secret-key" for req in captured)
    assert all(req.url.host == "api.stlouisfed.org" for req in captured)


def _sec_submissions_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "filings": {
                "recent": {
                    "form": ["10-K", "8-K"],
                    "filingDate": ["2026-09-01", "2026-09-18"],
                    "accessionNumber": ["0000320193-26-000001", "0000320193-26-000002"],
                    "primaryDocument": ["10k.htm", "8k.htm"],
                }
            }
        },
    )


def test_sec_edgar_fetch_returns_raw_documents_for_new_filings() -> None:
    connector = ApiConnector(
        http_client=_client_for(_sec_submissions_response),
        user_agent="trading-agent-research contact@example.com",
        cik_by_symbol={"AAPL": "320193"},
    )
    since = datetime(2026, 9, 10, tzinfo=timezone.utc)
    now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)

    documents = connector.fetch(_sec_edgar_source(), since, now=now)

    assert len(documents) == 1
    assert documents[0].source_id == "sec_edgar"
    assert "000032019326000002" in documents[0].url
    assert documents[0].fetched_at == now


def test_sec_edgar_fetch_requires_user_agent() -> None:
    connector = ApiConnector(
        http_client=_client_for(_sec_submissions_response),
        cik_by_symbol={"AAPL": "320193"},
    )
    with pytest.raises(ValueError, match="User-Agent"):
        connector.fetch(_sec_edgar_source(), datetime(2026, 9, 10, tzinfo=timezone.utc))


def test_sec_edgar_fetch_requires_cik_mapping() -> None:
    connector = ApiConnector(
        http_client=_client_for(_sec_submissions_response),
        user_agent="trading-agent-research contact@example.com",
    )
    with pytest.raises(ValueError, match="cik_by_symbol"):
        connector.fetch(_sec_edgar_source(), datetime(2026, 9, 10, tzinfo=timezone.utc))


def test_sec_edgar_fetch_sends_user_agent_header() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _sec_submissions_response(request)

    connector = ApiConnector(
        http_client=_client_for(handler),
        user_agent="trading-agent-research contact@example.com",
        cik_by_symbol={"AAPL": "320193"},
    )
    connector.fetch(_sec_edgar_source(), datetime(2026, 9, 10, tzinfo=timezone.utc))

    assert captured
    assert captured[0].headers["user-agent"] == "trading-agent-research contact@example.com"


def test_fetch_rejects_non_api_source() -> None:
    connector = ApiConnector(api_key="test-key")
    with pytest.raises(ValueError, match="cannot fetch source kind"):
        connector.fetch(_fred_source(kind="rss"), datetime(2026, 9, 16, tzinfo=timezone.utc))


def test_fetch_rejects_unknown_host() -> None:
    connector = ApiConnector(api_key="test-key")
    with pytest.raises(ValueError, match="no ApiConnector adapter"):
        connector.fetch(_fred_source(base_url="https://example.com/api"), datetime(2026, 9, 16, tzinfo=timezone.utc))


def test_throttle_sleeps_to_respect_configured_rate_limit() -> None:
    """rate_limit_per_min=120 -> interval minim 0.5s; time_fn constant simulează 2 request-uri instant."""
    sleeps: list[float] = []
    connector = ApiConnector(
        http_client=_client_for(_fred_observations_response),
        api_key="test-key",
        time_fn=lambda: 100.0,
        sleep_fn=sleeps.append,
    )
    source = _fred_source(rate_limit_per_min=120)

    connector._throttle(source)
    connector._throttle(source)

    assert sleeps == [0.5]


def test_throttle_does_not_sleep_when_no_rate_limit_configured() -> None:
    sleeps: list[float] = []
    connector = ApiConnector(
        http_client=_client_for(_fred_observations_response),
        api_key="test-key",
        time_fn=lambda: 100.0,
        sleep_fn=sleeps.append,
    )
    source = _fred_source(rate_limit_per_min=None)

    connector._throttle(source)
    connector._throttle(source)

    assert sleeps == []


def test_throttle_does_not_sleep_when_enough_time_elapsed() -> None:
    ticks = iter([100.0, 100.0, 101.0, 101.0])
    sleeps: list[float] = []
    connector = ApiConnector(
        http_client=_client_for(_fred_observations_response),
        api_key="test-key",
        time_fn=lambda: next(ticks),
        sleep_fn=sleeps.append,
    )
    source = _fred_source(rate_limit_per_min=120)

    connector._throttle(source)
    connector._throttle(source)

    assert sleeps == []
