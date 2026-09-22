"""Idempotent import of `audit_log` + `human_approvals` from frozen
`runtime/paper*` directories (design Phase 7, §8.10). Same "never guess, JSON
report out" contract as `scripts/db/import_execution.py` / `import_backtests.py`.

Only these two tables have a legacy on-disk source. `system_events`, `agent_runs`,
and `alerts` do not — this importer never touches them, and the report says so
explicitly rather than silently skipping (`unimported_tables` key), matching the
plan's "never fabricate history that was never recorded" posture.

Inputs, per `--runtime-root` (repeatable — pass one per frozen `runtime/paper*`
copy; never the live tree, copy it first):

- `audit/audit.sqlite` — **required**. Every row becomes one `audit_log` row.
- `control/approvals/*.request.json` (+ matching `*.decision.json`, optional —
  a request with no decision file was abandoned/never decided) — one
  `human_approvals` row per request file, `approval_id = correlation_id`.

Documented gaps (never fabricated):

- `human_approvals.expires_at` is NOT NULL, but `{cid}.request.json` on disk only
  ever recorded `requested_at` — the timeout itself was a live `ApprovalGate`
  constructor argument (`--config`'s `approval_timeout_s`), never persisted per
  request. The importer reconstructs it as `requested_at + approval_timeout_s`
  from `--paper-config` (defaults to `config/paper_trading.yaml`), the exact same
  source `ApprovalGate.request()` itself reads — every such row is flagged
  `expires_at_reconstructed: true` in the report (same honesty pattern as
  `import_backtests.py`'s `universe_sha256_reconstructed`).
- `order_id` links only when a matching `order_submitted` audit event exists for
  that correlation_id **and** an `orders` row with that id already exists in the
  destination database (i.e. `scripts/db/import_execution.py` already imported
  that same frozen runtime dir) — otherwise left NULL and counted in the report
  as `order_id_unresolved`, never guessed.
- A request file with no decision file (abandoned mid-approval, process killed
  before timeout) imports with `approved`/`decided_by`/`reason`/`decided_at` all
  NULL — a real "still pending" row, not an error.

Idempotency: `audit_log` has no natural PK from a historical import, so each row
is deduped on `(correlation_id, event_type, "timestamp")` (the exact original
recorded values) before INSERT. `human_approvals` keys off
`approval_id = correlation_id` (`ON CONFLICT DO NOTHING` for the request INSERT;
the decision fields are re-applied via `UPDATE` on every rerun so a decision file
that appears after an earlier dry pass is still picked up — this is idempotent
because it always writes the exact same values from the same frozen files).
Rerunning on the same frozen copy must not change any destination row count.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.audit.events import AuditEventType
from src.db.config import require_database_url
from src.db.pool import close_database_pools
from src.engine.paper_config import load_paper_trading_config

# The CHECK constraint in migrations/versions/0005_audit_agent_approvals.py is
# this exact list — imported from the same source-of-truth type the design DDL
# was written against (src/audit/events.py), not a second hand-copied list.
_VALID_EVENT_TYPES = frozenset(AuditEventType.__args__)  # type: ignore[attr-defined]


class QuarantineWriter:
    """JSONL sink, truncated at construction so a rerun on the same frozen copy
    reproduces the same file instead of accumulating duplicates across
    invocations."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._entries: list[dict[str, Any]] = []

    def add(self, reason: str, **detail: Any) -> None:
        self._entries.append({"reason": reason, **detail})

    def flush(self) -> int:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as handle:
            for entry in self._entries:
                handle.write(json.dumps(entry, default=str) + "\n")
        return len(self._entries)


@dataclass
class _ImportCounts:
    audit_log: int = 0
    human_approvals: int = 0
    expires_at_reconstructed: int = 0
    order_id_resolved: int = 0
    order_id_unresolved: int = 0
    quarantined: dict[str, int] = field(default_factory=dict)

    def bump_quarantine(self, reason: str) -> None:
        self.quarantined[reason] = self.quarantined.get(reason, 0) + 1


def _load_audit_rows(path: Path) -> list[dict[str, Any]]:
    """Every row from one frozen `audit.sqlite`, in insertion order."""
    rows: list[dict[str, Any]] = []
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        for row in connection.execute(
            "SELECT timestamp, correlation_id, event_type, payload "
            "FROM audit_events ORDER BY id ASC"
        ):
            rows.append(
                {
                    "timestamp": datetime.fromisoformat(row["timestamp"]),
                    "correlation_id": UUID(row["correlation_id"]),
                    "event_type": row["event_type"],
                    "payload": json.loads(row["payload"]),
                }
            )
    finally:
        connection.close()
    return rows


def _load_approval_files(runtime_root: Path) -> dict[UUID, dict[str, Any]]:
    """`approval_id -> {"request": {...}, "decision": {...} | None}`, one entry
    per `*.request.json` file (a decision file with no matching request file
    cannot happen — `write_approval`/`ScriptedApprovalOperator` only ever write a
    decision after `ApprovalGate.request()` already wrote the request)."""
    approvals_dir = runtime_root / "control" / "approvals"
    result: dict[UUID, dict[str, Any]] = {}
    if not approvals_dir.is_dir():
        return result
    for request_path in sorted(approvals_dir.glob("*.request.json")):
        correlation_id = UUID(request_path.name.removesuffix(".request.json"))
        request_payload = json.loads(request_path.read_text(encoding="utf-8"))
        decision_path = approvals_dir / f"{correlation_id}.decision.json"
        decision_payload = (
            json.loads(decision_path.read_text(encoding="utf-8"))
            if decision_path.is_file()
            else None
        )
        result[correlation_id] = {"request": request_payload, "decision": decision_payload}
    return result


def _audit_log_exists(
    connection: Any, *, correlation_id: UUID, event_type: str, timestamp: datetime
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1 FROM audit_log
            WHERE correlation_id = %s AND event_type = %s AND "timestamp" = %s
            """,
            (correlation_id, event_type, timestamp),
        ).fetchone()
        is not None
    )


def _import_audit_rows(
    connection: Any,
    rows: list[dict[str, Any]],
    *,
    quarantine: QuarantineWriter,
    counts: _ImportCounts,
    dry_run: bool,
) -> None:
    for row in rows:
        if row["event_type"] not in _VALID_EVENT_TYPES:
            quarantine.add(
                "unknown_event_type",
                correlation_id=str(row["correlation_id"]),
                event_type=row["event_type"],
            )
            counts.bump_quarantine("unknown_event_type")
            continue
        if _audit_log_exists(
            connection,
            correlation_id=row["correlation_id"],
            event_type=row["event_type"],
            timestamp=row["timestamp"],
        ):
            continue
        counts.audit_log += 1
        if dry_run:
            continue
        connection.execute(
            """
            INSERT INTO audit_log ("timestamp", correlation_id, event_type, payload)
            VALUES (%s, %s, %s, %s::jsonb)
            """,
            (
                row["timestamp"],
                row["correlation_id"],
                row["event_type"],
                json.dumps(row["payload"], default=str, sort_keys=True),
            ),
        )


def _resolve_order_id(
    connection: Any, audit_rows_by_correlation: dict[UUID, list[dict[str, Any]]], correlation_id: UUID
) -> UUID | None:
    """`order_id` links only when both a matching `order_submitted` audit event
    exists AND that id is already an `orders` row in the destination — never
    guessed, never inserted as a side effect of this importer."""
    events = audit_rows_by_correlation.get(correlation_id, [])
    if not any(event["event_type"] == "order_submitted" for event in events):
        return None
    row = connection.execute(
        "SELECT order_id FROM orders WHERE order_id = %s", (correlation_id,)
    ).fetchone()
    return row["order_id"] if row is not None else None


def _import_approvals(
    connection: Any,
    approvals: dict[UUID, dict[str, Any]],
    *,
    audit_rows_by_correlation: dict[UUID, list[dict[str, Any]]],
    approval_timeout_s: float,
    quarantine: QuarantineWriter,
    counts: _ImportCounts,
    dry_run: bool,
) -> None:
    for correlation_id, entry in approvals.items():
        request = entry["request"]
        decision = entry["decision"]
        try:
            requested_at = datetime.fromisoformat(request["requested_at"])
        except (KeyError, ValueError):
            quarantine.add(
                "invalid_request_payload", correlation_id=str(correlation_id), request=request
            )
            counts.bump_quarantine("invalid_request_payload")
            continue
        # Never persisted per-request on disk — reconstructed from the same
        # config source ApprovalGate.request() itself reads (see docstring).
        expires_at = requested_at + timedelta(seconds=approval_timeout_s)
        counts.expires_at_reconstructed += 1

        order_id = None
        approved = decided_by = reason = decided_at = None
        if decision is not None:
            approved = decision.get("approved")
            decided_by = decision.get("decided_by")
            reason = decision.get("reason")
            decided_at_raw = decision.get("decided_at")
            decided_at = datetime.fromisoformat(decided_at_raw) if decided_at_raw else None
            if approved:
                order_id = _resolve_order_id(connection, audit_rows_by_correlation, correlation_id)
                if order_id is not None:
                    counts.order_id_resolved += 1
                else:
                    counts.order_id_unresolved += 1
                    counts.bump_quarantine("order_id_unresolved")
                    quarantine.add(
                        "order_id_unresolved",
                        correlation_id=str(correlation_id),
                        detail=(
                            "approved but no matching order_submitted audit event, or "
                            "orders row not yet imported for this correlation_id"
                        ),
                    )

        counts.human_approvals += 1
        if dry_run:
            continue
        connection.execute(
            """
            INSERT INTO human_approvals
                (approval_id, order_id, requested_at, expires_at, request_payload)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (approval_id) DO NOTHING
            """,
            (
                correlation_id,
                order_id,
                requested_at,
                expires_at,
                json.dumps(request, default=str, sort_keys=True),
            ),
        )
        connection.execute(
            """
            UPDATE human_approvals
            SET order_id = COALESCE(human_approvals.order_id, %s),
                approved = %s, decided_by = %s, reason = %s, decided_at = %s
            WHERE approval_id = %s
            """,
            (order_id, approved, decided_by, reason, decided_at, correlation_id),
        )


def _destination_counts(connection: Any) -> dict[str, int]:
    def count(query: str) -> int:
        return connection.execute(query).fetchone()["count"]

    return {
        "audit_log": count("SELECT count(*) AS count FROM audit_log"),
        "human_approvals": count("SELECT count(*) AS count FROM human_approvals"),
    }


def import_audit(
    *,
    runtime_roots: list[Path],
    database_url: str,
    paper_config_path: Path = REPO_ROOT / "config/paper_trading.yaml",
    quarantine_path: Path,
    dry_run: bool,
) -> dict[str, Any]:
    quarantine = QuarantineWriter(quarantine_path)
    counts = _ImportCounts()
    config = load_paper_trading_config(paper_config_path)

    per_root: dict[str, dict[str, int]] = {}
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        for runtime_root in runtime_roots:
            audit_path = runtime_root / "audit" / "audit.sqlite"
            if not audit_path.is_file():
                raise ValueError(f"required audit.sqlite not found: {audit_path}")
            rows = _load_audit_rows(audit_path)
            audit_rows_by_correlation: dict[UUID, list[dict[str, Any]]] = {}
            for row in rows:
                audit_rows_by_correlation.setdefault(row["correlation_id"], []).append(row)

            before = (counts.audit_log, counts.human_approvals)
            _import_audit_rows(
                connection, rows, quarantine=quarantine, counts=counts, dry_run=dry_run
            )
            approvals = _load_approval_files(runtime_root)
            _import_approvals(
                connection,
                approvals,
                audit_rows_by_correlation=audit_rows_by_correlation,
                approval_timeout_s=config.approval_timeout_s,
                quarantine=quarantine,
                counts=counts,
                dry_run=dry_run,
            )
            per_root[str(runtime_root)] = {
                "audit_rows_seen": len(rows),
                "audit_log_imported": counts.audit_log - before[0],
                "approval_files_seen": len(approvals),
                "human_approvals_imported": counts.human_approvals - before[1],
            }

        destination_counts = _destination_counts(connection)

    close_database_pools()
    quarantine_count = quarantine.flush()

    return {
        "dry_run": dry_run,
        "runtime_roots": [str(root) for root in runtime_roots],
        "paper_config": str(paper_config_path),
        "per_root": per_root,
        "imported": {
            "audit_log": counts.audit_log,
            "human_approvals": counts.human_approvals,
        },
        "expires_at_reconstructed": counts.expires_at_reconstructed,
        "order_id_resolved": counts.order_id_resolved,
        "order_id_unresolved": counts.order_id_unresolved,
        "destination": destination_counts,
        "quarantine_path": str(quarantine_path),
        "quarantine_count": quarantine_count,
        "quarantine_reason_counts": counts.quarantined,
        "unimported_tables": {
            "system_events": "no legacy on-disk source (never existed before this phase)",
            "agent_runs": "no legacy on-disk source (never existed before this phase)",
            "alerts": "fully ephemeral until this phase; no historical ack/resolve trail on disk",
        },
        "idempotent_key": (
            'audit_log deduped on (correlation_id, event_type, "timestamp"); '
            "human_approvals keyed on approval_id=correlation_id, ON CONFLICT DO NOTHING "
            "+ re-applied UPDATE"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime-root",
        type=Path,
        action="append",
        required=True,
        dest="runtime_roots",
        help="Frozen copy of one runtime/paper* directory — repeatable, never the live tree",
    )
    parser.add_argument("--database-url", default=os.environ.get("MIGRATION_DATABASE_URL"))
    parser.add_argument(
        "--paper-config",
        type=Path,
        default=REPO_ROOT / "config/paper_trading.yaml",
        help="Source for approval_timeout_s used to reconstruct expires_at",
    )
    parser.add_argument("--quarantine", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    for root in args.runtime_roots:
        if not root.is_dir():
            raise SystemExit(f"--runtime-root not found: {root}")
    url = require_database_url(args.database_url, variable="MIGRATION_DATABASE_URL")
    quarantine_path = args.quarantine or (
        (args.report.parent if args.report else Path.cwd()) / "audit-quarantine.jsonl"
    )

    report = import_audit(
        runtime_roots=args.runtime_roots,
        database_url=url,
        paper_config_path=args.paper_config,
        quarantine_path=quarantine_path,
        dry_run=args.dry_run,
    )
    output = json.dumps(report, indent=2, default=str)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
