"""Rezervare client_order_id ÎNAINTE de submit — design §5 execution/."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from src.execution.types import OrderRequest, OrderResult


class DuplicateClientOrderId(Exception):
    """Rezervare repetată a aceluiași client_order_id."""

    def __init__(self, client_order_id: UUID, stored: OrderResult | None) -> None:
        self.client_order_id = client_order_id
        self.stored = stored
        super().__init__(f"client_order_id already reserved: {client_order_id}")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS reservations (
    client_order_id TEXT PRIMARY KEY,
    reserved_at TEXT NOT NULL,
    result_json TEXT
);
"""


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(_SCHEMA)
    return connection


class IdempotencyStore:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        with _connect(self._db_path) as connection:
            connection.commit()

    def reserve(
        self,
        client_order_id: UUID,
        *,
        order: OrderRequest | None = None,
        correlation_id: UUID | None = None,
    ) -> None:
        """INSERT înainte de submit. Duplicate → DuplicateClientOrderId.

        `order`/`correlation_id` are accepted for interface parity with
        `PostgresIdempotencyStore` (src/execution/postgres_store.py), which needs the
        full order + correlation to populate `orders`/`order_events`. SQLite ignores
        them — the on-disk reservation table only ever needed the id.
        """
        key = str(client_order_id)
        with _connect(self._db_path) as connection:
            existing = connection.execute(
                "SELECT result_json FROM reservations WHERE client_order_id = ?",
                (key,),
            ).fetchone()
            if existing is not None:
                stored = (
                    OrderResult.model_validate(json.loads(existing["result_json"]))
                    if existing["result_json"]
                    else None
                )
                raise DuplicateClientOrderId(client_order_id, stored)
            connection.execute(
                "INSERT INTO reservations (client_order_id, reserved_at, result_json) "
                "VALUES (?, ?, NULL)",
                (key, datetime.now(timezone.utc).isoformat()),
            )
            connection.commit()

    def store_result(self, result: OrderResult) -> None:
        with _connect(self._db_path) as connection:
            cursor = connection.execute(
                "UPDATE reservations SET result_json = ? WHERE client_order_id = ?",
                (result.model_dump_json(), str(result.client_order_id)),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    f"no reservation for client_order_id {result.client_order_id}"
                )
            connection.commit()

    def get_result(self, client_order_id: UUID) -> OrderResult | None:
        with _connect(self._db_path) as connection:
            row = connection.execute(
                "SELECT result_json FROM reservations WHERE client_order_id = ?",
                (str(client_order_id),),
            ).fetchone()
        if row is None or not row["result_json"]:
            return None
        return OrderResult.model_validate_json(row["result_json"])

    def reserved_ids(self) -> list[UUID]:
        with _connect(self._db_path) as connection:
            rows = connection.execute(
                "SELECT client_order_id FROM reservations ORDER BY reserved_at"
            ).fetchall()
        return [UUID(row["client_order_id"]) for row in rows]
