"""SQLite append-only. Fără UPDATE/DELETE expuse public."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from src.audit.events import AuditEvent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL
);
"""


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(_SCHEMA)
    return connection


class AuditLog:
    """Jurnal de audit. `record` e singurul verb public de scriere."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        with _connect(self._db_path) as connection:
            connection.commit()

    def record(self, event: AuditEvent) -> None:
        payload = json.dumps(event.payload, default=str, sort_keys=True)
        with _connect(self._db_path) as connection:
            connection.execute(
                "INSERT INTO audit_events (timestamp, correlation_id, event_type, payload) "
                "VALUES (?, ?, ?, ?)",
                (
                    event.timestamp.isoformat(),
                    str(event.correlation_id),
                    event.event_type,
                    payload,
                ),
            )
            connection.commit()

    def list_events(self, *, after_id: int = 0, limit: int | None = None) -> list[AuditEvent]:
        """Citire pentru rapoarte/watchdog — nu e mutație."""
        return [event for _, event in self.list_event_rows(after_id=after_id, limit=limit)]

    def list_event_rows(
        self, *, after_id: int = 0, limit: int | None = None
    ) -> list[tuple[int, AuditEvent]]:
        """Citire paginată cu id-ul de cursor. Fără mutație."""
        query = (
            "SELECT id, timestamp, correlation_id, event_type, payload "
            "FROM audit_events WHERE id > ? ORDER BY id ASC"
        )
        params: tuple[object, ...] = (after_id,)
        if limit is not None:
            query += " LIMIT ?"
            params = (after_id, limit)
        with _connect(self._db_path) as connection:
            rows = connection.execute(query, params).fetchall()
        events: list[tuple[int, AuditEvent]] = []
        for row in rows:
            events.append(
                (
                    int(row["id"]),
                    AuditEvent(
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        correlation_id=UUID(row["correlation_id"]),
                        event_type=row["event_type"],
                        payload=json.loads(row["payload"]),
                    ),
                )
            )
        return events
