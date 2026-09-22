"""Create backtest/paper-run entity schema (design Phase 6, §8.6).

Revision ID: 0004_backtest_paper_runs
Revises: 0003_execution_risk
Create Date: 2026-09-21

Deviations from docs/database-design.md §8.6 (documented per docs/database-cutover-
playbook.md convention, same as 0002/0003's notes):

- `backtest_runs.status` CHECK adds `queued` alongside the design's `running`/
  `completed`/`failed` — `src/control/backtest_jobs.py::BacktestJobManager` submits
  a job before it starts running. Job status `done` maps to `completed`, `error`
  maps to `failed` (see `src/engine/backtest_store.py`).
- `backtest_runs.universe_sha256` stays NOT NULL as designed. Going-forward writers
  hash `config/universe.yaml` at run start; imported job JSON that predates that
  hash gets the current file's hash and the importer report sets
  `universe_sha256_reconstructed: true` (same honesty pattern as
  `scripts/db/import_execution.py`'s `unresolved_history`).
- `paper_trading_runs` adds `UNIQUE (portfolio_id)`, not in the design DDL. The four
  `runtime/paper*` directories are long-lived runs, not one row per session
  (`sessions_count` already models accumulation across restarts) — a second row for
  the same portfolio would fragment that accumulation, and historical per-invocation
  rows cannot be reconstructed from `paper_run_summary.json` (it is overwritten in
  place, not appended).
- Index `backtest_runs (strategy_version_id, started_at DESC)` added for the
  `GET /v1/strategies/{id}/backtests` list endpoint (`src/control/server.py`).
"""

from alembic import op

revision = "0004_backtest_paper_runs"
down_revision = "0003_execution_risk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE backtest_runs (
            backtest_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            strategy_version_id UUID NOT NULL REFERENCES strategy_versions(strategy_version_id),
            instrument_id UUID NOT NULL REFERENCES instruments(instrument_id),
            data_source_id INT REFERENCES market_data_sources(source_id),
            timeframe TEXT NOT NULL,
            period_start TIMESTAMPTZ NOT NULL,
            period_end TIMESTAMPTZ NOT NULL,
            dataset_hash TEXT NOT NULL,
            universe_sha256 TEXT NOT NULL,
            random_seed INT,
            status TEXT NOT NULL DEFAULT 'running' CHECK (
                status IN ('queued', 'running', 'completed', 'failed')
            ),
            metrics JSONB,
            report_path TEXT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at TIMESTAMPTZ,
            created_by UUID REFERENCES users(user_id)
        );
        CREATE INDEX idx_backtest_runs_strategy_version_started
            ON backtest_runs (strategy_version_id, started_at DESC);

        CREATE TABLE backtest_trades (
            id BIGSERIAL PRIMARY KEY,
            backtest_run_id UUID NOT NULL REFERENCES backtest_runs(backtest_run_id),
            instrument_id UUID NOT NULL REFERENCES instruments(instrument_id),
            side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
            entry_time TIMESTAMPTZ NOT NULL,
            entry_price NUMERIC NOT NULL,
            exit_time TIMESTAMPTZ,
            exit_price NUMERIC,
            quantity NUMERIC NOT NULL,
            pnl NUMERIC,
            fees NUMERIC NOT NULL DEFAULT 0,
            exit_reason TEXT
        );
        CREATE INDEX idx_backtest_trades_run ON backtest_trades (backtest_run_id);

        CREATE TABLE paper_trading_runs (
            paper_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            portfolio_id UUID NOT NULL REFERENCES portfolios(portfolio_id),
            strategy_version_id UUID NOT NULL REFERENCES strategy_versions(strategy_version_id),
            instrument_id UUID NOT NULL REFERENCES instruments(instrument_id),
            config_snapshot JSONB NOT NULL,
            status TEXT NOT NULL DEFAULT 'running' CHECK (
                status IN ('running', 'stopped', 'halted')
            ),
            halt_reason TEXT,
            sessions_count INT NOT NULL DEFAULT 0,
            summary JSONB,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            stopped_at TIMESTAMPTZ,
            UNIQUE (portfolio_id)
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE paper_trading_runs;
        DROP TABLE backtest_trades;
        DROP TABLE backtest_runs;
        """
    )
