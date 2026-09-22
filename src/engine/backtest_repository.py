"""Backtest persistence boundary and backend selection (design Phase 6).

Mirrors `src/data/market_data_repository.py` / `src/execution/repository.py`: a
`backend` string selects `files` (the existing `backtests/jobs/*.json` +
`backtests/reports/` writes — always on, the rollback target) or `postgres`
(`backtest_runs`/`backtest_trades`, opt-in addition). Default stays `files`
(docs/database-cutover-playbook.md domain 4).
"""

from __future__ import annotations

from src.db.config import require_database_url


def open_backtest_store(*, backend: str, database_url: str | None):
    """Returns `None` for the `files` backend — `BacktestJobManager` and the CLI
    suite treat a `None` store as "Postgres writes disabled", never as an error;
    the unconditional JSON writes are unaffected either way."""
    normalized = backend.strip().lower()
    if normalized == "files":
        return None
    if normalized == "postgres":
        from src.engine.backtest_store import PostgresBacktestStore

        url = require_database_url(database_url, variable="BACKTEST_DATABASE_URL")
        return PostgresBacktestStore(url)
    raise ValueError("BACKTEST_STORE_BACKEND must be 'files' or 'postgres'")
