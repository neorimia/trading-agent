"""ApprovalGate — același flux în paper și live. Nu auto-aprobă intern."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.risk.risk_engine import RiskDecision

if TYPE_CHECKING:
    from src.audit.postgres_store import PostgresApprovalStore

_STRICT = ConfigDict(extra="forbid")


class ApprovalResult(BaseModel):
    model_config = _STRICT

    approved: bool
    correlation_id: UUID
    decided_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    decided_at: datetime


class ApprovalOperator(Protocol):
    """Scrie fișierul de decizie. Operatorul uman e un script/CLI, nu gateway-ul."""

    def decide(self, request_path: Path, decision_path: Path) -> None: ...


class FileApprovalOperator:
    """Nu scrie nimic — așteaptă un om (sau un alt proces) să pună decision.json."""

    def decide(self, request_path: Path, decision_path: Path) -> None:
        return None


class ScriptedApprovalOperator:
    """Simulează PO-ul scriind același fișier de decizie ca un om. Nu e bypass intern."""

    def __init__(self, *, approved: bool, decided_by: str = "paper-operator") -> None:
        self._approved = approved
        self._decided_by = decided_by

    def decide(self, request_path: Path, decision_path: Path) -> None:
        payload = {
            "approved": self._approved,
            "decided_by": self._decided_by,
            "reason": "scripted_approve" if self._approved else "scripted_reject",
            "decided_at": datetime.now(timezone.utc).isoformat(),
        }
        decision_path.write_text(json.dumps(payload), encoding="utf-8")


class ApprovalGate:
    def __init__(
        self,
        approvals_dir: str | Path,
        *,
        timeout_s: float = 3600.0,
        poll_interval_s: float = 0.05,
        operator: ApprovalOperator | None = None,
        approval_store: "PostgresApprovalStore | None" = None,
    ) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self._dir = Path(approvals_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._timeout_s = timeout_s
        self._poll_interval_s = poll_interval_s
        self._operator = operator if operator is not None else FileApprovalOperator()
        # AUDIT_STORE_BACKEND=postgres only (None on the files/rollback path). This
        # is the single writer for `human_approvals` — it is the one call that
        # observes both the request and the eventual decision, whichever process
        # (this one via ScriptedApprovalOperator, or control via write_approval())
        # wrote the decision file — so there is no second, racier writer. Exposed
        # publicly (not name-mangled) so PaperTradingLoop can reach it to link
        # `order_id` after a later, separate `order_submitted` step.
        self.approval_store = approval_store

    def request(self, order_intent: RiskDecision, correlation_id: UUID) -> ApprovalResult:
        request_path = self._dir / f"{correlation_id}.request.json"
        decision_path = self._dir / f"{correlation_id}.decision.json"
        requested_at = datetime.now(timezone.utc)
        risk_decision_payload = json.loads(order_intent.model_dump_json())
        request_path.write_text(
            json.dumps(
                {
                    "correlation_id": str(correlation_id),
                    "requested_at": requested_at.isoformat(),
                    "risk_decision": risk_decision_payload,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        expires_at = requested_at + timedelta(seconds=self._timeout_s)
        if self.approval_store is not None:
            self.approval_store.record_request(
                correlation_id=correlation_id,
                requested_at=requested_at,
                expires_at=expires_at,
                request_payload={"risk_decision": risk_decision_payload},
            )
        self._operator.decide(request_path, decision_path)
        deadline = time.monotonic() + self._timeout_s
        while time.monotonic() < deadline:
            if decision_path.is_file():
                result = self._load_decision(decision_path, correlation_id)
                self._record_decision(result)
                return result
            time.sleep(self._poll_interval_s)
        result = ApprovalResult(
            approved=False,
            correlation_id=correlation_id,
            decided_by="timeout",
            reason="approval_timeout",
            decided_at=datetime.now(timezone.utc),
        )
        self._record_decision(result)
        return result

    def _record_decision(self, result: ApprovalResult) -> None:
        if self.approval_store is None:
            return
        self.approval_store.record_decision(
            correlation_id=result.correlation_id,
            approved=result.approved,
            decided_by=result.decided_by,
            reason=result.reason,
            decided_at=result.decided_at,
        )

    @staticmethod
    def _load_decision(path: Path, correlation_id: UUID) -> ApprovalResult:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"approval decision must be an object: {path}")
        approved = raw.get("approved")
        decided_by = raw.get("decided_by")
        reason = raw.get("reason")
        decided_at_raw = raw.get("decided_at")
        if not isinstance(approved, bool):
            raise ValueError("approval decision.approved must be bool")
        if not isinstance(decided_by, str) or not decided_by.strip():
            raise ValueError("approval decision.decided_by must be a non-empty string")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("approval decision.reason must be a non-empty string")
        if not isinstance(decided_at_raw, str):
            raise ValueError("approval decision.decided_at must be an ISO timestamp")
        return ApprovalResult(
            approved=approved,
            correlation_id=correlation_id,
            decided_by=decided_by.strip(),
            reason=reason.strip(),
            decided_at=datetime.fromisoformat(decided_at_raw.replace("Z", "+00:00")),
        )
