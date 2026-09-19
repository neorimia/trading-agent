"""R1b — ApiConnector (FRED, ALFRED, SEC, BLS, BEA): mock HTTP, throttle explicit, zero rețea reală."""

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
        "review_status": "reviewed",
    }
    payload.update(overrides)
    return SourceConfig.model_validate(payload)


def _alfred_source(**overrides: object) -> SourceConfig:
    return _fred_source(source_id="alfred", name="ALFRED", **overrides)


def _sec_edgar_source(**overrides: object) -> SourceConfig:
    payload = {
        "source_id": "sec_edgar",
        "name": "SEC EDGAR",
        "kind": "api",
        "base_url": "https://data.sec.gov",
        "credibility_score": 0.98,
        "robots_txt_status": "not_applicable_api",
        "tos_reviewed_at": datetime(2026, 9, 18, tzinfo=timezone.utc),
        "rate_limit_per_min": None,
        "min_request_interval_s": 0.1,
        "review_status": "reviewed_with_dynamic_limit",
    }
    payload.update(overrides)
    return SourceConfig.model_validate(payload)


def _bls_source(**overrides: object) -> SourceConfig:
    payload = {
        "source_id": "bls",
        "name": "BLS",
        "kind": "api",
        "base_url": "https://api.bls.gov/publicAPI/v2",
        "credibility_score": 0.97,
        "robots_txt_status": "not_applicable_api",
        "tos_reviewed_at": datetime(2026, 9, 18, tzinfo=timezone.utc),
        "rate_limit_per_min": None,
        "min_request_interval_s": 0.2,
        "review_status": "reviewed",
    }
    payload.update(overrides)
    return SourceConfig.model_validate(payload)


def _bea_source(**overrides: object) -> SourceConfig:
    payload = {
        "source_id": "bea",
        "name": "BEA",
        "kind": "api",
        "base_url": "https://apps.bea.gov/api/data",
        "credibility_score": 0.97,
        "robots_txt_status": "not_applicable_api",
        "tos_reviewed_at": datetime(2026, 9, 18, tzinfo=timezone.utc),
        "rate_limit_per_min": 100,
        "review_status": "reviewed",
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
    assert all("realtime_end" not in req.url.params for req in captured)
    assert all("realtime_start" not in req.url.params for req in captured)


def test_alfred_sends_realtime_end_and_fred_live_does_not() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _fred_observations_response(request)

    connector = ApiConnector(
        http_client=_client_for(handler), api_key="secret-key", sleep_fn=lambda _: None
    )
    now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
    since = datetime(2026, 9, 16, tzinfo=timezone.utc)

    alfred_docs = connector.fetch(_alfred_source(), since, now=now)
    assert captured
    assert all(doc.source_id == "alfred" for doc in alfred_docs)
    assert all(req.url.params["realtime_start"] == "2026-09-18" for req in captured)
    assert all(req.url.params["realtime_end"] == "2026-09-18" for req in captured)

    captured.clear()
    connector.fetch(_fred_source(), since, now=now)
    assert captured
    assert all("realtime_end" not in req.url.params for req in captured)


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


def _sec_handler(request: httpx.Request) -> httpx.Response:
    if "companyfacts" in str(request.url):
        return httpx.Response(200, json={"cik": 320193, "facts": {}})
    return _sec_submissions_response(request)


def test_sec_edgar_fetch_returns_raw_documents_for_new_filings() -> None:
    connector = ApiConnector(
        http_client=_client_for(_sec_handler),
        user_agent="trading-agent-research contact@example.com",
        cik_by_symbol={"AAPL": "320193"},
        sleep_fn=lambda _: None,
    )
    since = datetime(2026, 9, 10, tzinfo=timezone.utc)
    now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)

    documents = connector.fetch(_sec_edgar_source(), since, now=now)

    urls = {doc.url for doc in documents}
    assert any("000032019326000002" in url for url in urls)
    assert any("companyfacts/CIK0000320193.json" in url for url in urls)
    assert all(doc.source_id == "sec_edgar" for doc in documents)
    assert all(doc.fetched_at == now for doc in documents)


def test_sec_edgar_fetch_requires_user_agent() -> None:
    connector = ApiConnector(
        http_client=_client_for(_sec_handler),
        cik_by_symbol={"AAPL": "320193"},
    )
    with pytest.raises(ValueError, match="User-Agent"):
        connector.fetch(_sec_edgar_source(), datetime(2026, 9, 10, tzinfo=timezone.utc))


def test_sec_edgar_fetch_requires_cik_mapping() -> None:
    connector = ApiConnector(
        http_client=_client_for(_sec_handler),
        user_agent="trading-agent-research contact@example.com",
    )
    with pytest.raises(ValueError, match="cik_by_symbol"):
        connector.fetch(_sec_edgar_source(), datetime(2026, 9, 10, tzinfo=timezone.utc))


def test_sec_edgar_skips_crypto_symbols() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _sec_handler(request)

    connector = ApiConnector(
        http_client=_client_for(handler),
        user_agent="trading-agent-research contact@example.com",
        cik_by_symbol={"BTCUSD": "1", "ETHUSD": "2", "AAPL": "320193"},
        sleep_fn=lambda _: None,
    )
    connector.fetch(_sec_edgar_source(), datetime(2026, 9, 10, tzinfo=timezone.utc))

    assert captured
    assert all("CIK0000320193" in str(req.url) for req in captured)
    assert all("CIK0000000001" not in str(req.url) for req in captured)


def test_sec_edgar_crypto_only_mapping_is_rejected() -> None:
    connector = ApiConnector(
        http_client=_client_for(_sec_handler),
        user_agent="trading-agent-research contact@example.com",
        cik_by_symbol={"BTCUSD": "1", "ETH": "2"},
    )
    with pytest.raises(ValueError, match="cik_by_symbol"):
        connector.fetch(_sec_edgar_source(), datetime(2026, 9, 10, tzinfo=timezone.utc))


def test_sec_edgar_fetch_sends_user_agent_header() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _sec_handler(request)

    connector = ApiConnector(
        http_client=_client_for(handler),
        user_agent="trading-agent-research contact@example.com",
        cik_by_symbol={"AAPL": "320193"},
        sleep_fn=lambda _: None,
    )
    connector.fetch(_sec_edgar_source(), datetime(2026, 9, 10, tzinfo=timezone.utc))

    assert captured
    assert captured[0].headers["user-agent"] == "trading-agent-research contact@example.com"


def test_bls_fetch_returns_raw_documents() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "Results": {
                    "series": [
                        {
                            "seriesID": "CUUR0000SA0",
                            "data": [
                                {"year": "2025", "period": "M12", "value": "300.0"},
                                {"year": "2026", "period": "M08", "value": "314.2"},
                            ],
                        }
                    ]
                }
            },
        )

    connector = ApiConnector(http_client=_client_for(handler), sleep_fn=lambda _: None)
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    documents = connector.fetch(_bls_source(), since, now=now)

    assert captured[0].method == "POST"
    assert captured[0].url.host == "api.bls.gov"
    assert any("CUUR0000SA0#2026-M08" in doc.url for doc in documents)
    assert all("2025" not in doc.url for doc in documents)


def test_bea_fetch_retries_after_429() -> None:
    captured: list[httpx.Request] = []
    sleeps: list[float] = []
    ticks = iter([100.0, 110.0, 120.0, 130.0, 140.0, 150.0])

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if len(captured) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, json={"BEAAPI": {"Results": {}}})

    connector = ApiConnector(
        http_client=_client_for(handler),
        bea_api_key="bea-key",
        time_fn=lambda: next(ticks),
        sleep_fn=sleeps.append,
    )
    documents = connector.fetch(
        _bea_source(),
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        now=datetime(2026, 9, 18, tzinfo=timezone.utc),
    )

    assert len(captured) == 2
    assert captured[0].url.params["UserID"] == "bea-key"
    assert sleeps == [2.0]
    assert documents
    assert documents[0].source_id == "bea"


def test_bea_fetch_requires_api_key() -> None:
    connector = ApiConnector(http_client=_client_for(lambda _: httpx.Response(200)))
    with pytest.raises(ValueError, match="api_key"):
        connector.fetch(_bea_source(), datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_fetch_rejects_non_api_source() -> None:
    connector = ApiConnector(api_key="test-key")
    with pytest.raises(ValueError, match="cannot fetch source kind"):
        connector.fetch(_fred_source(kind="rss"), datetime(2026, 9, 16, tzinfo=timezone.utc))


def test_fetch_rejects_unknown_host() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200)

    connector = ApiConnector(http_client=_client_for(handler), api_key="test-key")
    with pytest.raises(ValueError, match="no ApiConnector adapter"):
        connector.fetch(
            _fred_source(source_id="unknown_portal", base_url="https://example.com/api"),
            datetime(2026, 9, 16, tzinfo=timezone.utc),
        )
    assert captured == []


def test_fetch_pending_source_raises_without_http() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _fred_observations_response(request)

    connector = ApiConnector(
        http_client=_client_for(handler), api_key="test-key", sleep_fn=lambda _: None
    )
    pending = _fred_source(review_status="pending", tos_reviewed_at=None)
    with pytest.raises(ValueError, match="not fetchable"):
        connector.fetch(pending, datetime(2026, 9, 16, tzinfo=timezone.utc))
    assert captured == []


def test_reviewed_with_dynamic_limit_requires_min_interval() -> None:
    connector = ApiConnector(
        http_client=_client_for(_sec_handler),
        user_agent="trading-agent-research contact@example.com",
        cik_by_symbol={"AAPL": "320193"},
    )
    source = _sec_edgar_source(min_request_interval_s=None)
    with pytest.raises(ValueError, match="min_request_interval_s"):
        connector.fetch(source, datetime(2026, 9, 10, tzinfo=timezone.utc))


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


def test_sec_throttle_uses_min_request_interval_not_per_min() -> None:
    sleeps: list[float] = []
    connector = ApiConnector(
        http_client=_client_for(_sec_handler),
        user_agent="trading-agent-research contact@example.com",
        time_fn=lambda: 100.0,
        sleep_fn=sleeps.append,
    )
    source = _sec_edgar_source()

    connector._throttle(source)
    connector._throttle(source)

    assert sleeps == [0.1]


def test_throttle_prefers_min_request_interval_over_per_min() -> None:
    sleeps: list[float] = []
    connector = ApiConnector(
        http_client=_client_for(_fred_observations_response),
        api_key="test-key",
        time_fn=lambda: 100.0,
        sleep_fn=sleeps.append,
    )
    source = _bls_source()

    connector._throttle(source)
    connector._throttle(source)

    assert sleeps == [0.2]


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
