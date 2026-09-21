"""Execution persistence boundary and backend selection (design Phases 3+4).

Mirrors `src/data/market_data_repository.py` / `src/research/repository.py`: a
`backend` string selects `json` (SQLite reservations + the JSON snapshot files
`PaperTradingLoop` already writes — the rollback target) or `postgres` (`orders` /
`order_events` / `executions` / `balances` / `positions` / `signals` /
`risk_events`). Default stays `json` (docs/database-cutover-playbook.md).
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from src.db.config import require_database_url
from src.execution.idempotency_store import IdempotencyStore
from src.execution.order_gateway import IdempotencyStoreProtocol


def open_idempotency_store(
    *,
    backend: str,
    sqlite_path: str | Path,
    database_url: str | None,
    portfolio_id: UUID | None = None,
    strategy_version_id: UUID | None = None,
    risk_limits_version_id: UUID | None = None,
    trading_mode: str = "paper",
) -> IdempotencyStoreProtocol:
    normalized = backend.strip().lower()
    if normalized == "json":
        return IdempotencyStore(sqlite_path)
    if normalized == "postgres":
        from src.execution.postgres_store import PostgresIdempotencyStore

        url = require_database_url(database_url, variable="EXECUTION_DATABASE_URL")
        if portfolio_id is None:
            raise ValueError("portfolio_id is required for the postgres backend")
        return PostgresIdempotencyStore(
            url,
            portfolio_id=portfolio_id,
            strategy_version_id=strategy_version_id,
            risk_limits_version_id=risk_limits_version_id,
            trading_mode=trading_mode,
        )
    raise ValueError("EXECUTION_STORE_BACKEND must be 'json' or 'postgres'")


def open_portfolio_store(
    *,
    database_url: str,
    portfolio_id: UUID,
    signal_source: str,
    risk_limits_version_id: UUID | None,
):
    """Only constructed when `EXECUTION_STORE_BACKEND=postgres` — the JSON path has
    no equivalent class; `PaperTradingLoop._persist_local_state` always writes the
    JSON snapshot files regardless of backend (no dual-write flag, but the on-disk
    write is unconditional so the rollback files never go stale)."""
    from src.execution.postgres_store import PostgresPortfolioStore

    return PostgresPortfolioStore(
        database_url,
        portfolio_id=portfolio_id,
        signal_source=signal_source,
        risk_limits_version_id=risk_limits_version_id,
    )
