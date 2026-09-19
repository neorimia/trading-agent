"""Server LLM: loopback only, POST /propose orchestrează generate + universe."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.llm.schema import LLMAnalysis, LLMProposal, RejectedAnalysis, RejectedProposal
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


def _analysis_ok() -> LLMAnalysis:
    return LLMAnalysis.model_validate(
        {
            "asset": "ETHUSD",
            "timestamp": "2026-09-18T12:00:00+00:00",
            "timeframe": "1d",
            "analysis_type": "technical",
            "factual_summary": "EMA fast above slow.",
            "data_sources": [{"url": "kraken:ohlc"}],
            "bullish_case": "hold",
            "bearish_case": "break",
            "neutral_case": "range",
            "key_assumptions": ["spot"],
            "catalysts": ["unknown"],
            "risks": ["liq"],
            "invalidation_conditions": ["close below slow"],
            "confidence_score": 0.4,
            "data_quality_score": 0.6,
            "uncertainty": "no funding",
            "recommended_action": "hold",
            "action_type": "research_only",
            "position_size_suggestion": None,
            "required_human_approval": True,
            "expiry_time": "2026-09-19T12:00:00+00:00",
            "audit_metadata": {
                "model_name": "qwen3:8b",
                "prompt_hash": "aa",
                "facts_bundle_hash": "bb",
                "temperature": 0.0,
                "schema_version": "analysis.v1",
            },
        }
    )


def test_analyze_returns_research_report(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.llm.server.generate_analysis", lambda context, config, **kwargs: _analysis_ok())
    with TestClient(app) as client:
        response = client.post(
            "/analyze",
            json={
                "instrument": "ETHUSD",
                "as_of": datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc).isoformat(),
                "analysis_type": "technical",
                "timeframe": "1d",
                "facts_bundle": {"close": "2410"},
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["asset"] == "ETHUSD"
    assert body["position_size_suggestion"] is None
    assert body["required_human_approval"] is True
    assert "reason" not in body


def test_analyze_rejects_out_of_universe(monkeypatch: pytest.MonkeyPatch) -> None:
    analysis = _analysis_ok()
    monkeypatch.setattr(
        "src.llm.server.generate_analysis",
        lambda context, config, **kwargs: analysis.model_copy(update={"asset": "NOTREAL"}),
    )
    with TestClient(app) as client:
        response = client.post(
            "/analyze",
            json={
                "instrument": "NOTREAL",
                "as_of": datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc).isoformat(),
                "analysis_type": "technical",
                "facts_bundle": {},
            },
        )
    assert response.status_code == 200
    assert response.json()["reason"] == "instrument_not_in_universe"


def test_analyze_forwards_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.llm.server.generate_analysis",
        lambda context, config, **kwargs: RejectedAnalysis(reason="schema_invalid", raw_output="nope"),
    )
    with TestClient(app) as client:
        response = client.post(
            "/analyze",
            json={
                "instrument": "ETHUSD",
                "as_of": datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc).isoformat(),
                "analysis_type": "technical",
                "facts_bundle": {},
            },
        )
    assert response.status_code == 200
    assert response.json()["reason"] == "schema_invalid"
