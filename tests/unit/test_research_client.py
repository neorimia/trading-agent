"""ResearchClient: fail-open spre None la orice eroare — niciodată excepție necontrolată."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from src.engine.research_client import ResearchClient


def _client(handler) -> ResearchClient:
    http = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://127.0.0.1:8766",
    )
    return ResearchClient(base_url="http://127.0.0.1:8766", http_client=http)


def _as_of() -> datetime:
    return datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def test_get_context_parses_external_context() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/context"
        assert request.url.params["instrument"] == "AAPL"
        return httpx.Response(
            200,
            json={
                "instrument": "AAPL",
                "as_of": _as_of().isoformat(),
                "external_context": "EXTERNAL CONTEXT for AAPL as of ...",
                "sources": ["https://example.com/a"],
                "generated_at": _as_of().isoformat(),
                "document_count": 1,
            },
        )

    result = _client(handler).get_context("AAPL", _as_of())
    assert result == "EXTERNAL CONTEXT for AAPL as of ..."


def test_get_context_returns_none_on_204() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    assert _client(handler).get_context("AAPL", _as_of()) is None


def test_get_context_returns_none_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("late")

    assert _client(handler).get_context("AAPL", _as_of()) is None


def test_get_context_returns_none_on_connect_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("research process is down")

    assert _client(handler).get_context("AAPL", _as_of()) is None


def test_get_context_returns_none_on_5xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    assert _client(handler).get_context("AAPL", _as_of()) is None


def test_get_context_returns_none_on_malformed_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    assert _client(handler).get_context("AAPL", _as_of()) is None


def test_get_context_returns_none_when_external_context_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"instrument": "AAPL"})

    assert _client(handler).get_context("AAPL", _as_of()) is None


def test_get_context_never_raises_on_any_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.RemoteProtocolError("garbage response")

    result = _client(handler).get_context("AAPL", _as_of())
    assert result is None
