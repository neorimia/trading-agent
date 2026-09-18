"""AuditLog append-only — fără update/delete publice."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.audit.audit_log import AuditLog
from src.audit.events import AuditEvent


def test_record_appends_and_preserves_order(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.sqlite")
    cid = uuid4()
    first = AuditEvent.now(correlation_id=cid, event_type="proposal", payload={"n": 1})
    second = AuditEvent.now(correlation_id=cid, event_type="risk_decision", payload={"n": 2})
    log.record(first)
    log.record(second)
    events = log.list_events()
    assert [e.event_type for e in events] == ["proposal", "risk_decision"]
    assert events[0].payload == {"n": 1}
    assert events[0].correlation_id == cid


def test_record_has_no_update_or_delete_api() -> None:
    assert not hasattr(AuditLog, "update")
    assert not hasattr(AuditLog, "delete")
    assert not hasattr(AuditLog, "remove")


def test_timestamp_roundtrip(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.sqlite")
    moment = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
    event = AuditEvent(
        timestamp=moment,
        correlation_id=uuid4(),
        event_type="halt",
        payload={"reason": "test"},
    )
    log.record(event)
    loaded = log.list_events()[0]
    assert loaded.timestamp == moment
    assert loaded.payload["reason"] == "test"
