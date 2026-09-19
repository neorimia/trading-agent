"""Contract AuditEvent — design §4.5, plus evenimente de reconciliere din §8.4."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")

AuditEventType = Literal[
    "proposal",
    "rejected_proposal",
    "risk_decision",
    "human_approval",
    "order_submitted",
    "fill",
    "halt",
    "reconciliation_ok",
    "reconciliation_mismatch",
    "operator_action",
]


class AuditEvent(BaseModel):
    """Eveniment imutabil. `payload` e serializarea completă a obiectului sursă."""

    model_config = _STRICT

    timestamp: datetime
    correlation_id: UUID
    event_type: AuditEventType
    payload: dict[str, Any]

    @classmethod
    def now(
        cls,
        *,
        correlation_id: UUID,
        event_type: AuditEventType,
        payload: dict[str, Any],
    ) -> AuditEvent:
        return cls(
            timestamp=datetime.now(timezone.utc),
            correlation_id=correlation_id,
            event_type=event_type,
            payload=payload,
        )
