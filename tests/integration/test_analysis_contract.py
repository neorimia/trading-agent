"""Sincronizare llm.schema.LLMAnalysis ↔ engine.analysis_types.ParsedAnalysis."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.engine.analysis_types import ParsedAnalysis
from src.llm.schema import LLMAnalysis

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "llm_analyses.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _outcome(model, payload: dict) -> str:
    try:
        model.model_validate(payload)
        return "accept"
    except ValidationError:
        return "reject"


@pytest.mark.parametrize(
    "case",
    _load_fixture()["analysis_cases"],
    ids=lambda case: case["name"],
)
def test_analysis_schemas_agree(case: dict) -> None:
    expected = case["expect"]
    payload = case["payload"]
    llm_result = _outcome(LLMAnalysis, payload)
    engine_result = _outcome(ParsedAnalysis, payload)
    assert llm_result == expected
    assert engine_result == expected
    assert llm_result == engine_result
