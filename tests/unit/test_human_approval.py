"""ApprovalGate — același flux fișier; operatorul scrie decision.json."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from src.execution.human_approval import (
    ApprovalGate,
    FileApprovalOperator,
    ScriptedApprovalOperator,
)
from src.risk.risk_engine import RiskDecision


def _decision() -> RiskDecision:
    return RiskDecision(
        approved=True,
        instrument="ETHUSD",
        side="buy",
        quantity=Decimal("0.1"),
        reject_reason=None,
        requires_human_approval=True,
    )


def test_scripted_operator_approves_via_decision_file(tmp_path: Path) -> None:
    cid = uuid4()
    gate = ApprovalGate(
        tmp_path,
        timeout_s=1.0,
        poll_interval_s=0.01,
        operator=ScriptedApprovalOperator(approved=True, decided_by="po"),
    )
    result = gate.request(_decision(), cid)
    assert result.approved is True
    assert result.decided_by == "po"
    assert (tmp_path / f"{cid}.request.json").is_file()
    assert (tmp_path / f"{cid}.decision.json").is_file()


def test_scripted_operator_can_reject(tmp_path: Path) -> None:
    gate = ApprovalGate(
        tmp_path,
        timeout_s=1.0,
        operator=ScriptedApprovalOperator(approved=False),
    )
    result = gate.request(_decision(), uuid4())
    assert result.approved is False


def test_timeout_without_decision_file(tmp_path: Path) -> None:
    gate = ApprovalGate(
        tmp_path,
        timeout_s=0.05,
        poll_interval_s=0.01,
        operator=FileApprovalOperator(),
    )
    result = gate.request(_decision(), uuid4())
    assert result.approved is False
    assert result.reason == "approval_timeout"
