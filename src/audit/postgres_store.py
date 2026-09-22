"""PostgreSQL stores for audit/agent/approvals entities (design Phase 7, §8.10).

Dual-write posture, matching Phases 2-6: SQLite (`audit.sqlite`) and the JSON
approval files stay the unconditional rollback target; PostgreSQL writes are
additive only, gated by `AUDIT_STORE_BACKEND=postgres`. Reads stay on SQLite/JSON —
Postgres is not the control-plane read path yet (that is Faza 8, out of scope here).

Ownership split (see docs/database-cutover-playbook.md domain 5 / plan for the full
rationale):

- `audit_log` — written by both control and engine via `open_audit_log()`, a
  drop-in `AuditLog` subclass that writes SQLite unconditionally and additionally
  INSERTs into Postgres.
- `human_approvals` — written *entirely* by the engine's `ApprovalGate.request()`
  (`src/execution/human_approval.py`): it is the one call that observes both the
  request and the eventual decision (whichever process wrote the decision file),
  so a single writer avoids a second, racier writer in `write_approval()`.
- `agent_runs` — written by the engine (`scripts/paper_trading/run_paper_session.py`):
  INSERT at process start, UPDATE at graceful shutdown.
- `system_events` — written by control (`src/control/agent_process.py`, the
  heartbeat-stale watchdog) for operational, non-trading events.
- `alerts` — written by control from `build_alerts()`; ack/resolve via the two new
  `/v1/alerts/{alert_id}/...` endpoints.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from src.audit.audit_log import AuditLog
from src.audit.events import AuditEvent
from src.db.config import require_database_url
from src.db.pool import get_database_pool


def _payload_json(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str, sort_keys=True)


class DualWriteAuditLog(AuditLog):
    """`AuditLog` drop-in: SQLite write is unconditional (delegated to the parent
    class), the Postgres INSERT is additive on top. Every read method
    (`list_events`/`list_event_rows`) is inherited unchanged — SQLite stays the
    read path."""

    def __init__(self, db_path: str | Path, *, database_url: str) -> None:
        super().__init__(db_path)
        self._database_url = database_url

    def record(self, event: AuditEvent) -> None:
        super().record(event)
        pool = get_database_pool(self._database_url)
        with pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO audit_log ("timestamp", correlation_id, event_type, payload)
                VALUES (%s, %s, %s, %s::jsonb)
                """,
                (
                    event.timestamp,
                    str(event.correlation_id),
                    event.event_type,
                    _payload_json(event.payload),
                ),
            )


def open_audit_log(
    db_path: str | Path, *, backend: str, database_url: str | None = None
) -> AuditLog:
    """`files` (default) returns the plain SQLite-only `AuditLog`. `postgres`
    returns a dual-write drop-in — every existing call site just swaps the
    constructor, no other code changes."""
    normalized = backend.strip().lower()
    if normalized == "files":
        return AuditLog(db_path)
    if normalized == "postgres":
        url = require_database_url(database_url, variable="AUDIT_DATABASE_URL")
        return DualWriteAuditLog(db_path, database_url=url)
    raise ValueError("AUDIT_STORE_BACKEND must be 'files' or 'postgres'")


class PostgresApprovalStore:
    """`human_approvals` — INSERT at request time, UPDATE at decision time, and a
    best-effort UPDATE to link `order_id` once an order is actually submitted
    (only possible when `EXECUTION_STORE_BACKEND=postgres` too, since that is what
    populates the `orders` row `order_id` references — otherwise left NULL, never
    guessed)."""

    def __init__(self, database_url: str) -> None:
        self._pool = get_database_pool(database_url)

    def record_request(
        self,
        *,
        correlation_id: UUID,
        requested_at: datetime,
        expires_at: datetime,
        request_payload: dict[str, Any],
    ) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO human_approvals
                    (approval_id, requested_at, expires_at, request_payload)
                VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (approval_id) DO NOTHING
                """,
                (
                    str(correlation_id),
                    requested_at,
                    expires_at,
                    _payload_json(request_payload),
                ),
            )

    def record_decision(
        self,
        *,
        correlation_id: UUID,
        approved: bool,
        decided_by: str,
        reason: str,
        decided_at: datetime,
    ) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """
                UPDATE human_approvals
                SET approved = %s, decided_by = %s, reason = %s, decided_at = %s
                WHERE approval_id = %s
                """,
                (approved, decided_by, reason, decided_at, str(correlation_id)),
            )

    def link_order(self, *, correlation_id: UUID, order_id: UUID) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                "UPDATE human_approvals SET order_id = %s WHERE approval_id = %s",
                (str(order_id), str(correlation_id)),
            )


class PostgresAgentRunStore:
    """`agent_runs` — one row per engine process lifetime. INSERT at start
    (returns `agent_run_id`), UPDATE `stopped_at`/`stop_reason` at graceful
    shutdown. A hard kill (`kill -9`) leaves `stopped_at` NULL — not fabricated,
    same honesty posture as every other unresolvable gap in this codebase."""

    def __init__(self, database_url: str) -> None:
        self._pool = get_database_pool(database_url)

    def start_run(
        self,
        *,
        portfolio_id: UUID | None,
        strategy_version_id: UUID,
        trading_mode: str,
        config_snapshot: dict[str, Any],
        git_commit: str | None,
        host: str | None,
        pid: int | None,
    ) -> UUID:
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO agent_runs
                    (portfolio_id, trading_mode, strategy_version_id, git_commit,
                     config_snapshot, host, pid)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
                RETURNING agent_run_id
                """,
                (
                    str(portfolio_id) if portfolio_id else None,
                    trading_mode,
                    str(strategy_version_id),
                    git_commit,
                    _payload_json(config_snapshot),
                    host,
                    pid,
                ),
            ).fetchone()
        assert row is not None
        return UUID(str(row["agent_run_id"]))

    def finish_run(self, agent_run_id: UUID, *, stop_reason: str | None) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """
                UPDATE agent_runs SET stopped_at = now(), stop_reason = %s
                WHERE agent_run_id = %s
                """,
                (stop_reason, str(agent_run_id)),
            )


def current_git_commit(repo_root: Path) -> str | None:
    """Best-effort — never raises. `None` when the process is not running from a
    git checkout (e.g. a packaged deploy) or `git` is unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    commit = result.stdout.strip()
    return commit or None


def record_system_event(
    database_url: str,
    *,
    severity: str,
    component: str,
    event_type: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> None:
    pool = get_database_pool(database_url)
    with pool.connection() as connection:
        connection.execute(
            """
            INSERT INTO system_events (severity, component, event_type, message, payload)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            (severity, component, event_type, message, _payload_json(payload)),
        )


def record_alerts(database_url: str, alerts: list[Any]) -> None:
    """Insert a new `alerts` row only for a `title` with no currently-unresolved
    row — dedup on that natural key so a live poll/WS push does not spam a new row
    every call. `build_alerts()` stays the live/ephemeral read path; this is an
    additive persisted trail, not a replacement for it."""
    pool = get_database_pool(database_url)
    with pool.connection() as connection:
        for alert in alerts:
            existing = connection.execute(
                "SELECT 1 FROM alerts WHERE title = %s AND resolved_at IS NULL",
                (alert.title,),
            ).fetchone()
            if existing is not None:
                continue
            connection.execute(
                """
                INSERT INTO alerts (severity, title, detail, persistent)
                VALUES (%s, %s, %s, %s)
                """,
                (alert.severity, alert.title, alert.detail, alert.persistent),
            )


def ack_alert(database_url: str, alert_id: UUID, *, acknowledged_by: UUID | None) -> bool:
    pool = get_database_pool(database_url)
    with pool.connection() as connection:
        row = connection.execute(
            """
            UPDATE alerts SET acknowledged_at = now(), acknowledged_by = %s
            WHERE alert_id = %s AND acknowledged_at IS NULL
            RETURNING alert_id
            """,
            (str(acknowledged_by) if acknowledged_by else None, str(alert_id)),
        ).fetchone()
    return row is not None


def resolve_alert(database_url: str, alert_id: UUID) -> bool:
    pool = get_database_pool(database_url)
    with pool.connection() as connection:
        row = connection.execute(
            """
            UPDATE alerts SET resolved_at = now()
            WHERE alert_id = %s AND resolved_at IS NULL
            RETURNING alert_id
            """,
            (str(alert_id),),
        ).fetchone()
    return row is not None
