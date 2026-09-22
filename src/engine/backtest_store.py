"""PostgreSQL backtest store — design Phase 6 (docs/database-design.md §8.6).

Mirrors `src/data/postgres_store.py` / `src/execution/postgres_store.py`. Two call
sites write through this module:

- `src/control/backtest_jobs.py::BacktestJobManager` — one `backtest_runs` row per
  async job (`running` -> `completed`/`failed`).
- `scripts/backtest/run_backtest.py` — one `backtest_runs` row per
  `metrics_{kind}_{Nx}.json` in a CLI suite (`metrics.suite_run_id` in that row's
  `metrics` JSONB links the siblings; the design has no separate suite table, see
  `docs/database-cutover-playbook.md` domain 4 / the Phase 6 plan).

JSON files (`backtests/jobs/*.json`, `backtests/reports/`) stay the rollback target
and are always written first, unconditionally — this store is only the opt-in
addition (`BACKTEST_STORE_BACKEND=postgres`), never a replacement.

Deviation from the Phase 6 plan text: a job's Postgres row is created once its
`dataset_hash` is actually known (right after bars are fetched, immediately before
`run_backtest`), not at `submit()` time — `backtest_runs.dataset_hash` is NOT NULL
and this codebase's importers/stores never write a guessed placeholder for a NOT
NULL column (same posture as `scripts/db/import_execution.py`'s quarantine
philosophy). The row is inserted directly with `status='running'`; the JSON job
file still carries the real `queued` state in the interim.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from src.db.pool import get_database_pool

_TERMINAL_STATUSES = frozenset({"completed", "failed"})


def compute_universe_sha256(universe_path: Path) -> str:
    """Hash of `config/universe.yaml` at run start (0004_backtest_paper_runs.py
    deviations note: `universe_sha256` stays NOT NULL; the importer hashes the
    *current* file and flags `universe_sha256_reconstructed: true` for legacy job
    JSON that predates this field, instead of fabricating a historical value)."""
    digest = hashlib.sha256()
    digest.update(universe_path.read_bytes())
    return digest.hexdigest()


class PostgresBacktestStore:
    """`backtest_runs`/`backtest_trades` writer, using the `backtest_writer` role."""

    def __init__(self, database_url: str) -> None:
        self._pool = get_database_pool(database_url)

    def close(self) -> None:
        """Pool lifetime belongs to the process, not an individual request."""

    @staticmethod
    def _instrument_id(connection: Any, canonical_symbol: str) -> UUID:
        row = connection.execute(
            "SELECT instrument_id FROM instruments WHERE canonical_symbol = %s",
            (canonical_symbol,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown instrument symbol {canonical_symbol!r}")
        return row["instrument_id"]

    @staticmethod
    def _data_source_id(connection: Any, source_name: str | None) -> int | None:
        if source_name is None:
            return None
        row = connection.execute(
            "SELECT source_id FROM market_data_sources WHERE name = %s",
            (source_name,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown market data source {source_name!r}")
        return row["source_id"]

    def resolve_active_strategy_version_id(self, strategy_id: str) -> UUID | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT strategy_version_id FROM strategy_versions
                WHERE strategy_id = %s AND is_active = true
                ORDER BY version DESC LIMIT 1
                """,
                (strategy_id,),
            ).fetchone()
        return row["strategy_version_id"] if row is not None else None

    def insert_run(
        self,
        *,
        strategy_version_id: UUID,
        instrument: str,
        data_source_name: str | None = None,
        timeframe: str,
        period_start: datetime,
        period_end: datetime,
        dataset_hash: str,
        universe_sha256: str,
        random_seed: int | None = None,
        status: str = "running",
        metrics: dict[str, Any] | None = None,
        report_path: str | None = None,
        finished_at: datetime | None = None,
    ) -> UUID:
        finished = finished_at
        if finished is None and status in _TERMINAL_STATUSES:
            finished = datetime.now(timezone.utc)
        with self._pool.connection() as connection:
            with connection.transaction():
                instrument_id = self._instrument_id(connection, instrument)
                data_source_id = self._data_source_id(connection, data_source_name)
                row = connection.execute(
                    """
                    INSERT INTO backtest_runs (
                        strategy_version_id, instrument_id, data_source_id, timeframe,
                        period_start, period_end, dataset_hash, universe_sha256,
                        random_seed, status, metrics, report_path, finished_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s
                    )
                    RETURNING backtest_run_id
                    """,
                    (
                        strategy_version_id,
                        instrument_id,
                        data_source_id,
                        timeframe,
                        period_start,
                        period_end,
                        dataset_hash,
                        universe_sha256,
                        random_seed,
                        status,
                        json.dumps(metrics) if metrics is not None else None,
                        report_path,
                        finished,
                    ),
                ).fetchone()
        return row["backtest_run_id"]

    def update_run_status(
        self,
        backtest_run_id: UUID,
        *,
        status: str,
        metrics: dict[str, Any] | None = None,
        report_path: str | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        finished = finished_at
        if finished is None and status in _TERMINAL_STATUSES:
            finished = datetime.now(timezone.utc)
        with self._pool.connection() as connection:
            connection.execute(
                """
                UPDATE backtest_runs SET
                    status = %s,
                    metrics = COALESCE(%s::jsonb, metrics),
                    report_path = COALESCE(%s, report_path),
                    finished_at = COALESCE(%s, finished_at)
                WHERE backtest_run_id = %s
                """,
                (
                    status,
                    json.dumps(metrics) if metrics is not None else None,
                    report_path,
                    finished,
                    backtest_run_id,
                ),
            )

    def insert_trades(
        self,
        backtest_run_id: UUID,
        instrument: str,
        records: list[dict[str, Any]],
    ) -> int:
        """Append-only (design §8.6) — always INSERTs. Callers must not call this
        twice for the same `backtest_run_id`; the going-forward writers
        (`BacktestJobManager`, the CLI suite) call it exactly once, right after the
        run finishes and before marking the row `completed`."""
        if not records:
            return 0
        with self._pool.connection() as connection:
            with connection.transaction():
                instrument_id = self._instrument_id(connection, instrument)
                for record in records:
                    connection.execute(
                        """
                        INSERT INTO backtest_trades (
                            backtest_run_id, instrument_id, side, entry_time, entry_price,
                            exit_time, exit_price, quantity, pnl, fees, exit_reason
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            backtest_run_id,
                            instrument_id,
                            record["side"],
                            record["entry_time"],
                            Decimal(str(record["entry_price"])),
                            record.get("exit_time"),
                            (
                                Decimal(str(record["exit_price"]))
                                if record.get("exit_price") is not None
                                else None
                            ),
                            Decimal(str(record["quantity"])),
                            Decimal(str(record["pnl"])) if record.get("pnl") is not None else None,
                            Decimal(str(record.get("fees", "0"))),
                            record.get("exit_reason"),
                        ),
                    )
        return len(records)
