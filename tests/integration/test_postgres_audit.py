"""PostgreSQL audit/agent/approvals/alerts/system-events entities: constraints,
role isolation, the `agent_actions` view, and the importer (design Phase 7,
docs/database-design.md §8.10)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from scripts.db.import_audit import import_audit
from scripts.db.seed import seed_execution_reference_data, seed_reference_data
from src.audit.audit_log import AuditLog
from src.audit.events import AuditEvent
from src.db.pool import close_database_pools

pytestmark = pytest.mark.postgres
REPO_ROOT = Path(__file__).resolve().parents[2]


def _admin_database_url() -> str:
    value = os.environ.get("ADMIN_DATABASE_URL") or os.environ.get("MIGRATION_DATABASE_URL")
    if not value:
        pytest.skip("ADMIN_DATABASE_URL is not configured")
    return value


def _audit_database_url() -> str:
    """The audit_writer application role, shared by control + engine in production."""
    value = os.environ.get("AUDIT_DATABASE_URL")
    if not value:
        pytest.skip("AUDIT_DATABASE_URL is not configured")
    return value


def _control_database_url() -> str:
    value = os.environ.get("CONTROL_DATABASE_URL")
    if not value:
        pytest.skip("CONTROL_DATABASE_URL is not configured")
    return value


@pytest.fixture(autouse=True)
def clean_database() -> None:
    url = _admin_database_url()
    close_database_pools()
    with psycopg.connect(url) as connection:
        connection.execute(
            """
            TRUNCATE
                alerts, human_approvals, system_events, audit_log, agent_runs,
                backtest_trades, backtest_runs, paper_trading_runs,
                risk_events, executions, order_events, orders, signals,
                positions, balances, strategy_versions, strategies, risk_limits,
                portfolios
            RESTART IDENTITY CASCADE
            """
        )
        seed_reference_data(
            connection,
            universe_path=REPO_ROOT / "config/universe.yaml",
            sources_path=REPO_ROOT / "config/research_sources.yaml",
        )
        seed_execution_reference_data(
            connection,
            strategies_path=REPO_ROOT / "config/strategies.yaml",
            strategy_versions_dir=REPO_ROOT / "config/strategy_versions",
            risk_limits_path=REPO_ROOT / "config/risk_limits.yaml",
            paper_config_path=REPO_ROOT / "config/paper_trading.yaml",
        )
        connection.commit()
    yield
    close_database_pools()


def _active_strategy_version_id(connection: psycopg.Connection, strategy_id: str) -> UUID:
    row = connection.execute(
        """
        SELECT strategy_version_id FROM strategy_versions
        WHERE strategy_id = %s AND is_active = true ORDER BY version DESC LIMIT 1
        """,
        (strategy_id,),
    ).fetchone()
    assert row is not None
    return row[0]


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------


def test_audit_log_event_type_check_rejects_invalid_value() -> None:
    admin_url = _admin_database_url()
    with psycopg.connect(admin_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                """
                INSERT INTO audit_log (correlation_id, event_type, payload)
                VALUES (%s, 'not_a_real_event_type', '{}'::jsonb)
                """,
                (uuid4(),),
            )


def test_system_events_severity_check_rejects_invalid_value() -> None:
    admin_url = _admin_database_url()
    with psycopg.connect(admin_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                """
                INSERT INTO system_events (severity, component, event_type, message)
                VALUES ('not_a_real_severity', 'control', 'agent_start', 'x')
                """
            )


def test_agent_runs_trading_mode_check_rejects_invalid_value() -> None:
    admin_url = _admin_database_url()
    with psycopg.connect(admin_url) as connection:
        strategy_version_id = _active_strategy_version_id(connection, "baseline_ema_cross")
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                """
                INSERT INTO agent_runs (trading_mode, strategy_version_id, config_snapshot)
                VALUES ('not_a_real_mode', %s, '{}'::jsonb)
                """,
                (strategy_version_id,),
            )


def test_alerts_severity_check_rejects_invalid_value() -> None:
    admin_url = _admin_database_url()
    with psycopg.connect(admin_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                """
                INSERT INTO alerts (severity, title, detail) VALUES ('not_a_real_severity', 't', 'd')
                """
            )


def test_human_approvals_allows_pending_row_with_nullable_decision_fields() -> None:
    """The documented deviation (migration 0005 docstring): order_id/decided_by/
    reason are nullable — a freshly requested, not-yet-decided approval is a real
    row, not an error."""
    admin_url = _admin_database_url()
    cid = uuid4()
    with psycopg.connect(admin_url) as connection:
        connection.execute(
            """
            INSERT INTO human_approvals (approval_id, requested_at, expires_at, request_payload)
            VALUES (%s, now(), now() + interval '1 hour', '{}'::jsonb)
            """,
            (cid,),
        )
        row = connection.execute(
            "SELECT order_id, decided_by, reason, approved FROM human_approvals WHERE approval_id = %s",
            (cid,),
        ).fetchone()
        assert row == (None, None, None, None)


# ---------------------------------------------------------------------------
# agent_actions view
# ---------------------------------------------------------------------------


def test_agent_actions_view_returns_only_narrative_event_types() -> None:
    admin_url = _admin_database_url()
    narrative = {
        "proposal",
        "rejected_proposal",
        "risk_decision",
        "order_submitted",
        "halt",
        "operator_action",
    }
    non_narrative = {"fill", "reconciliation_ok", "analysis"}
    with psycopg.connect(admin_url) as connection:
        for event_type in narrative | non_narrative:
            connection.execute(
                """
                INSERT INTO audit_log (correlation_id, event_type, payload)
                VALUES (%s, %s, '{}'::jsonb)
                """,
                (uuid4(), event_type),
            )
        rows = connection.execute("SELECT event_type FROM agent_actions").fetchall()
        assert {row[0] for row in rows} == narrative


# ---------------------------------------------------------------------------
# Role isolation (deploy/postgres/create_roles.sql)
# ---------------------------------------------------------------------------


def test_audit_writer_can_insert_audit_log_but_not_update_or_delete() -> None:
    audit_url = _audit_database_url()
    cid = uuid4()
    with psycopg.connect(audit_url) as connection:
        connection.execute(
            """
            INSERT INTO audit_log (correlation_id, event_type, payload)
            VALUES (%s, 'halt', '{}'::jsonb)
            """,
            (cid,),
        )
    with psycopg.connect(audit_url) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "UPDATE audit_log SET event_type = 'fill' WHERE correlation_id = %s", (cid,)
            )
    with psycopg.connect(audit_url) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("DELETE FROM audit_log WHERE correlation_id = %s", (cid,))


def test_audit_writer_can_insert_and_update_human_approvals_agent_runs_alerts_system_events() -> None:
    audit_url = _audit_database_url()
    admin_url = _admin_database_url()
    with psycopg.connect(admin_url) as connection:
        strategy_version_id = _active_strategy_version_id(connection, "baseline_ema_cross")

    cid = uuid4()
    with psycopg.connect(audit_url) as connection:
        connection.execute(
            """
            INSERT INTO human_approvals (approval_id, requested_at, expires_at, request_payload)
            VALUES (%s, now(), now() + interval '1 hour', '{}'::jsonb)
            """,
            (cid,),
        )
        connection.execute(
            "UPDATE human_approvals SET approved = true, decided_by = 'op', reason = 'ok', "
            "decided_at = now() WHERE approval_id = %s",
            (cid,),
        )

        run_row = connection.execute(
            """
            INSERT INTO agent_runs (trading_mode, strategy_version_id, config_snapshot)
            VALUES ('paper', %s, '{}'::jsonb) RETURNING agent_run_id
            """,
            (strategy_version_id,),
        ).fetchone()
        connection.execute(
            "UPDATE agent_runs SET stopped_at = now(), stop_reason = 'completed' WHERE agent_run_id = %s",
            (run_row[0],),
        )

        alert_row = connection.execute(
            "INSERT INTO alerts (severity, title, detail) VALUES ('warning', 't', 'd') "
            "RETURNING alert_id"
        ).fetchone()
        connection.execute(
            "UPDATE alerts SET acknowledged_at = now() WHERE alert_id = %s", (alert_row[0],)
        )

        connection.execute(
            "INSERT INTO system_events (severity, component, event_type, message) "
            "VALUES ('info', 'control', 'agent_start', 'x')"
        )


def test_audit_writer_cannot_delete_agent_runs() -> None:
    audit_url = _audit_database_url()
    admin_url = _admin_database_url()
    with psycopg.connect(admin_url) as connection:
        strategy_version_id = _active_strategy_version_id(connection, "baseline_ema_cross")
    with psycopg.connect(audit_url) as connection:
        row = connection.execute(
            """
            INSERT INTO agent_runs (trading_mode, strategy_version_id, config_snapshot)
            VALUES ('paper', %s, '{}'::jsonb) RETURNING agent_run_id
            """,
            (strategy_version_id,),
        ).fetchone()
    with psycopg.connect(audit_url) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("DELETE FROM agent_runs WHERE agent_run_id = %s", (row[0],))


def test_control_reader_can_select_new_tables_and_view_but_not_write() -> None:
    admin_url = _admin_database_url()
    with psycopg.connect(admin_url) as connection:
        connection.execute(
            """
            INSERT INTO audit_log (correlation_id, event_type, payload)
            VALUES (%s, 'halt', '{}'::jsonb)
            """,
            (uuid4(),),
        )
    with psycopg.connect(_control_database_url()) as connection:
        for table in ("agent_runs", "audit_log", "agent_actions", "system_events",
                      "human_approvals", "alerts"):
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "INSERT INTO audit_log (correlation_id, event_type, payload) "
                "VALUES (%s, 'halt', '{}'::jsonb)",
                (uuid4(),),
            )


# ---------------------------------------------------------------------------
# Importer (scripts/db/import_audit.py)
# ---------------------------------------------------------------------------


def _write_fixture_runtime_root(root: Path, *, approved: bool = True) -> tuple[UUID, UUID]:
    """One correlation with a full proposal -> human_approval -> order_submitted
    chain, plus a second, rejected correlation with no order. Mirrors the shape
    `PaperTradingLoop.run_bar` actually records."""
    audit = AuditLog(root / "audit" / "audit.sqlite")
    approved_cid = uuid4()
    rejected_cid = uuid4()
    audit.record(
        AuditEvent.now(correlation_id=approved_cid, event_type="proposal", payload={"x": 1})
    )
    audit.record(
        AuditEvent.now(
            correlation_id=approved_cid, event_type="human_approval", payload={"approved": True}
        )
    )
    audit.record(
        AuditEvent.now(
            correlation_id=approved_cid, event_type="order_submitted", payload={"status": "filled"}
        )
    )
    audit.record(
        AuditEvent.now(correlation_id=rejected_cid, event_type="proposal", payload={"x": 2})
    )
    audit.record(
        AuditEvent.now(
            correlation_id=rejected_cid, event_type="human_approval", payload={"approved": False}
        )
    )

    approvals_dir = root / "control" / "approvals"
    approvals_dir.mkdir(parents=True, exist_ok=True)
    requested_at = datetime.now(timezone.utc)

    def _write_pair(cid: UUID, *, decided_approved: bool) -> None:
        (approvals_dir / f"{cid}.request.json").write_text(
            json.dumps(
                {
                    "correlation_id": str(cid),
                    "requested_at": requested_at.isoformat(),
                    "risk_decision": {},
                }
            ),
            encoding="utf-8",
        )
        (approvals_dir / f"{cid}.decision.json").write_text(
            json.dumps(
                {
                    "approved": decided_approved,
                    "decided_by": "paper-operator",
                    "reason": "scripted_approve" if decided_approved else "scripted_reject",
                    "decided_at": requested_at.isoformat(),
                }
            ),
            encoding="utf-8",
        )

    _write_pair(approved_cid, decided_approved=True)
    _write_pair(rejected_cid, decided_approved=False)
    return approved_cid, rejected_cid


def test_importer_populates_audit_log_and_human_approvals(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime" / "paper"
    approved_cid, rejected_cid = _write_fixture_runtime_root(runtime_root)
    admin_url = _admin_database_url()

    report = import_audit(
        runtime_roots=[runtime_root],
        database_url=admin_url,
        quarantine_path=tmp_path / "quarantine.jsonl",
        dry_run=False,
    )

    assert report["imported"]["audit_log"] == 5
    assert report["imported"]["human_approvals"] == 2
    assert report["destination"] == {"audit_log": 5, "human_approvals": 2}
    # order_id can never link (import_execution.py was never run for this
    # fixture — no `orders` row exists to reference), never guessed.
    assert report["order_id_unresolved"] == 1
    assert report["order_id_resolved"] == 0

    with psycopg.connect(admin_url) as connection:
        row = connection.execute(
            "SELECT approved, decided_by, order_id FROM human_approvals WHERE approval_id = %s",
            (approved_cid,),
        ).fetchone()
        assert row[0] is True
        assert row[1] == "paper-operator"
        assert row[2] is None

        row = connection.execute(
            "SELECT approved FROM human_approvals WHERE approval_id = %s", (rejected_cid,)
        ).fetchone()
        assert row[0] is False


def test_importer_dry_run_writes_nothing(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime" / "paper"
    _write_fixture_runtime_root(runtime_root)
    admin_url = _admin_database_url()

    report = import_audit(
        runtime_roots=[runtime_root],
        database_url=admin_url,
        quarantine_path=tmp_path / "quarantine.jsonl",
        dry_run=True,
    )

    assert report["imported"]["audit_log"] == 5
    assert report["imported"]["human_approvals"] == 2
    with psycopg.connect(admin_url) as connection:
        assert connection.execute("SELECT count(*) FROM audit_log").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM human_approvals").fetchone()[0] == 0


def test_importer_rerun_on_same_frozen_copy_is_idempotent(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime" / "paper"
    _write_fixture_runtime_root(runtime_root)
    admin_url = _admin_database_url()
    kwargs = dict(
        runtime_roots=[runtime_root],
        database_url=admin_url,
        quarantine_path=tmp_path / "quarantine.jsonl",
        dry_run=False,
    )

    first = import_audit(**kwargs)
    second = import_audit(**kwargs)

    assert first["destination"] == second["destination"] == {"audit_log": 5, "human_approvals": 2}
    # Nothing new the second time — audit_log rows are found via the existence
    # check, human_approvals via ON CONFLICT DO NOTHING + a re-applied UPDATE.
    assert second["per_root"][str(runtime_root)]["audit_log_imported"] == 0
