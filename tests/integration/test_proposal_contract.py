"""Sincronizare llm.schema ↔ engine.proposal_types (design §7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.engine.proposal_types import ParsedProposal
from src.engine.proposal_types import RejectedProposal as EngineRejected
from src.llm.schema import LLMProposal
from src.llm.schema import RejectedProposal as LlmRejected

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "llm_proposals.json"


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
    _load_fixture()["proposal_cases"],
    ids=lambda case: case["name"],
)
def test_proposal_schemas_agree(case: dict) -> None:
    expected = case["expect"]
    payload = case["payload"]
    llm_result = _outcome(LLMProposal, payload)
    engine_result = _outcome(ParsedProposal, payload)
    assert llm_result == expected
    assert engine_result == expected
    assert llm_result == engine_result


@pytest.mark.parametrize(
    "case",
    _load_fixture()["rejected_cases"],
    ids=lambda case: case["name"],
)
def test_rejected_schemas_agree(case: dict) -> None:
    expected = case["expect"]
    payload = case["payload"]
    llm_result = _outcome(LlmRejected, payload)
    engine_result = _outcome(EngineRejected, payload)
    assert llm_result == expected
    assert engine_result == expected
    assert llm_result == engine_result
