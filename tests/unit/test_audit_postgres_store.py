"""Dual-write posture for Phase 7 stores (design §8.10) — fake Postgres pool, no
real database. Mirrors `tests/unit/test_backtest_jobs_postgres_store.py`: prove
SQLite/JSON stays unconditional and the Postgres branch is additive-only, gated
on the backend flag."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from src.audit.audit_log import AuditLog
from src.audit.events import AuditEvent
from src.audit.postgres_store import DualWriteAuditLog, open_audit_log, record_alerts
from src.control.models import AlertRow
from src.execution.human_approval import ApprovalGate, ScriptedApprovalOperator
from src.risk.risk_engine import RiskDecision
from decimal import Decimal


class _FakeResult:
    def __init__(self, row: Any = None) -> None:
        self._row = row

    def fetchone(self) -> Any:
        return self._row


class _FakeConnection:
    """Records every `execute()` call; `fetchone_results` is consumed in order
    for tests that need a specific `RETURNING`/`SELECT` result."""

    def __init__(self, fetchone_results: list[Any] | None = None) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self._fetchone_results = list(fetchone_results or [])

    def execute(self, sql: str, params: tuple = ()) -> _FakeResult:
        self.calls.append((" ".join(sql.split()), params))
        if self._fetchone_results:
            return _FakeResult(self._fetchone_results.pop(0))
        return _FakeResult(None)


class _FakePool:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    @contextmanager
    def connection(self):
        yield self._connection


def _decision() -> RiskDecision:
    return RiskDecision(
        approved=True,
        instrument="ETHUSD",
        side="buy",
        quantity=Decimal("0.1"),
        reject_reason=None,
        requires_human_approval=True,
    )


# ---------------------------------------------------------------------------
# open_audit_log / DualWriteAuditLog
# ---------------------------------------------------------------------------


def test_open_audit_log_files_backend_returns_plain_auditlog(tmp_path: Path) -> None:
    log = open_audit_log(tmp_path / "audit.sqlite", backend="files")
    assert type(log) is AuditLog


def test_open_audit_log_postgres_backend_requires_database_url(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        open_audit_log(tmp_path / "audit.sqlite", backend="postgres", database_url=None)


def test_open_audit_log_invalid_backend_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        open_audit_log(tmp_path / "audit.sqlite", backend="not_a_backend")


def test_dual_write_audit_log_writes_sqlite_unconditionally_and_inserts_postgres(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_connection = _FakeConnection()
    monkeypatch.setattr(
        "src.audit.postgres_store.get_database_pool", lambda url: _FakePool(fake_connection)
    )
    log = DualWriteAuditLog(
        tmp_path / "audit.sqlite", database_url="postgresql://u:p@127.0.0.1:5432/db"
    )
    correlation_id = uuid4()
    event = AuditEvent.now(correlation_id=correlation_id, event_type="halt", payload={"x": 1})
    log.record(event)

    # SQLite write is unconditional — same read path (list_events) as the plain
    # AuditLog, regardless of the Postgres branch below.
    events = log.list_events()
    assert len(events) == 1
    assert events[0].correlation_id == correlation_id

    # Postgres INSERT additionally happened, with the same event data.
    assert len(fake_connection.calls) == 1
    sql, params = fake_connection.calls[0]
    assert sql.startswith("INSERT INTO audit_log")
    assert params[1] == str(correlation_id)
    assert params[2] == "halt"


# ---------------------------------------------------------------------------
# ApprovalGate.approval_store wiring (human_approvals)
# ---------------------------------------------------------------------------


class _FakeApprovalStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def record_request(self, **kwargs: Any) -> None:
        self.calls.append(("record_request", kwargs))

    def record_decision(self, **kwargs: Any) -> None:
        self.calls.append(("record_decision", kwargs))

    def link_order(self, **kwargs: Any) -> None:
        self.calls.append(("link_order", kwargs))

    def method_names(self) -> list[str]:
        return [name for name, _ in self.calls]


def test_approval_gate_without_store_never_touches_it(tmp_path: Path) -> None:
    """Default (`approval_store=None`, files/rollback path) — unchanged behavior,
    no store calls possible (there is no store)."""
    gate = ApprovalGate(
        tmp_path, timeout_s=1.0, operator=ScriptedApprovalOperator(approved=True)
    )
    result = gate.request(_decision(), uuid4())
    assert result.approved is True
    assert gate.approval_store is None


def test_approval_gate_records_request_then_decision_in_order(tmp_path: Path) -> None:
    store = _FakeApprovalStore()
    cid = uuid4()
    gate = ApprovalGate(
        tmp_path,
        timeout_s=1.0,
        poll_interval_s=0.01,
        operator=ScriptedApprovalOperator(approved=True, decided_by="po"),
        approval_store=store,
    )
    result = gate.request(_decision(), cid)

    assert result.approved is True
    assert store.method_names() == ["record_request", "record_decision"]
    request_call = store.calls[0][1]
    assert request_call["correlation_id"] == cid
    assert request_call["expires_at"] > request_call["requested_at"]
    decision_call = store.calls[1][1]
    assert decision_call["correlation_id"] == cid
    assert decision_call["approved"] is True
    assert decision_call["decided_by"] == "po"


def test_approval_gate_records_decision_on_timeout(tmp_path: Path) -> None:
    from src.execution.human_approval import FileApprovalOperator

    store = _FakeApprovalStore()
    gate = ApprovalGate(
        tmp_path,
        timeout_s=0.05,
        poll_interval_s=0.01,
        operator=FileApprovalOperator(),
        approval_store=store,
    )
    result = gate.request(_decision(), uuid4())

    assert result.approved is False
    assert result.decided_by == "timeout"
    assert store.method_names() == ["record_request", "record_decision"]
    decision_call = store.calls[1][1]
    assert decision_call["approved"] is False
    assert decision_call["decided_by"] == "timeout"


# ---------------------------------------------------------------------------
# record_alerts dedup
# ---------------------------------------------------------------------------


class _FakeAlertsConnection:
    """Simulates `alerts` state: a title is "unresolved" once inserted, so a
    second call for the same title must not INSERT again."""

    def __init__(self) -> None:
        self.inserted_titles: list[str] = []
        self._unresolved_titles: set[str] = set()

    def execute(self, sql: str, params: tuple = ()) -> _FakeResult:
        text = " ".join(sql.split())
        if text.startswith("SELECT 1 FROM alerts"):
            title = params[0]
            return _FakeResult({"1": 1} if title in self._unresolved_titles else None)
        if text.startswith("INSERT INTO alerts"):
            _, title, _, _ = params
            self.inserted_titles.append(title)
            self._unresolved_titles.add(title)
            return _FakeResult(None)
        raise AssertionError(f"unexpected SQL in fake alerts connection: {text}")


def test_record_alerts_skips_an_already_open_alert_of_the_same_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_connection = _FakeAlertsConnection()
    monkeypatch.setattr(
        "src.audit.postgres_store.get_database_pool", lambda url: _FakePool(fake_connection)
    )
    alert = AlertRow(
        id="halt", severity="error", title="Trading halted", detail="halt_flag present"
    )

    record_alerts("postgresql://u:p@127.0.0.1:5432/db", [alert])
    record_alerts("postgresql://u:p@127.0.0.1:5432/db", [alert])

    # Second call finds the title still unresolved and does not insert again —
    # this is the "no duplicate spam on every poll" dedup the plan requires.
    assert fake_connection.inserted_titles == ["Trading halted"]


def test_record_alerts_inserts_two_different_titles(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_connection = _FakeAlertsConnection()
    monkeypatch.setattr(
        "src.audit.postgres_store.get_database_pool", lambda url: _FakePool(fake_connection)
    )
    alerts = [
        AlertRow(id="halt", severity="error", title="Trading halted", detail="d1"),
        AlertRow(id="llm", severity="warning", title="LLM service unreachable", detail="d2"),
    ]

    record_alerts("postgresql://u:p@127.0.0.1:5432/db", alerts)

    assert fake_connection.inserted_titles == ["Trading halted", "LLM service unreachable"]
