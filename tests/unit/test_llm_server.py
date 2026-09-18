"""Server LLM: loopback only, POST /propose orchestrează generate + universe."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.llm.schema import LLMProposal, RejectedProposal
from src.llm.server import app, assert_no_broker_keys, validate_bind_host


def _payload(**overrides) -> dict:
    body = {
        "instrument": "AAPL",
        "as_of": datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc).isoformat(),
        "market_summary": "flat tape",
        "external_context": None,
    }
    body.update(overrides)
    return body


def test_validate_bind_host_accepts_loopback() -> None:
    assert validate_bind_host("127.0.0.1") == "127.0.0.1"
    assert validate_bind_host("localhost") == "localhost"


def test_validate_bind_host_rejects_wildcard() -> None:
    with pytest.raises(ValueError, match="loopback"):
        validate_bind_host("0.0.0.0")


def test_assert_no_broker_keys_rejects_engine_vars() -> None:
    with pytest.raises(RuntimeError, match="BROKER_API_KEY"):
        assert_no_broker_keys({"BROKER_API_KEY": "paper"})


def test_assert_no_broker_keys_rejects_kraken_spot_key() -> None:
    with pytest.raises(RuntimeError, match="KRAKEN_SPOT_API_KEY"):
        assert_no_broker_keys({"KRAKEN_SPOT_API_KEY": "live"})


def test_assert_no_broker_keys_allows_llm_env() -> None:
    assert_no_broker_keys(
        {
            "OLLAMA_HOST": "http://127.0.0.1:11434",
            "LLM_MODEL_NAME": "qwen3:8b",
        }
    )


def test_propose_returns_proposal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.llm.server.generate_proposal",
        lambda context, config, **kwargs: LLMProposal(
            instrument="AAPL",
            direction="avoid",
            confidence=0.2,
            rationale="no edge",
        ),
    )
    with TestClient(app) as client:
        response = client.post("/propose", json=_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["instrument"] == "AAPL"
    assert "reason" not in body


def test_propose_rejects_out_of_universe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.llm.server.generate_proposal",
        lambda context, config, **kwargs: LLMProposal(
            instrument="NOTREAL",
            direction="long",
            confidence=0.9,
            rationale="invented",
        ),
    )
    with TestClient(app) as client:
        response = client.post("/propose", json=_payload(instrument="NOTREAL"))
    assert response.status_code == 200
    body = response.json()
    assert body["reason"] == "instrument_not_in_universe"


def test_propose_forwards_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.llm.server.generate_proposal",
        lambda context, config, **kwargs: RejectedProposal(
            reason="schema_invalid",
            raw_output="not json",
        ),
    )
    with TestClient(app) as client:
        response = client.post("/propose", json=_payload())
    assert response.status_code == 200
    assert response.json()["reason"] == "schema_invalid"
