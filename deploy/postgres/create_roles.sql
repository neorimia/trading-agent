\set ON_ERROR_STOP on
\if :{?database_name}
\else
\set database_name trading_research
\endif

-- Supply passwords with psql variables:
-- psql ... -v research_password='...' -v control_password='...' \
--      -v market_data_password='...' -v execution_password='...' \
--      -v backtest_password='...' -v audit_password='...' -f create_roles.sql
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'research_writer') THEN
        CREATE ROLE research_writer LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'control_reader') THEN
        CREATE ROLE control_reader LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_data_writer') THEN
        CREATE ROLE market_data_writer LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'execution_writer') THEN
        CREATE ROLE execution_writer LOGIN;
    END IF;
    -- Control submits/finishes backtest jobs (src/control/backtest_jobs.py); it is
    -- read-only today (control_reader), so this is a new writer rather than a
    -- widened reader — mirrors the execution_writer/research_writer split.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'backtest_writer') THEN
        CREATE ROLE backtest_writer LOGIN;
    END IF;
    -- Audit/approvals/agent-runs/alerts/system-events (Phase 7) are written by
    -- BOTH control (src/control/runtime_state.py, agent_process.py) and the engine
    -- (scripts/paper_trading/run_paper_session.py) — unlike every role above, which
    -- has exactly one owning process, so a single shared writer role is used by
    -- both AUDIT_DATABASE_URL connections rather than splitting it in two.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'audit_writer') THEN
        CREATE ROLE audit_writer LOGIN;
    END IF;
END
$$;

ALTER ROLE research_writer PASSWORD :'research_password';
ALTER ROLE control_reader PASSWORD :'control_password';
ALTER ROLE market_data_writer PASSWORD :'market_data_password';
ALTER ROLE execution_writer PASSWORD :'execution_password';
ALTER ROLE backtest_writer PASSWORD :'backtest_password';
ALTER ROLE audit_writer PASSWORD :'audit_password';

GRANT CONNECT ON DATABASE :"database_name"
    TO research_writer, control_reader, market_data_writer, execution_writer,
       backtest_writer, audit_writer;
GRANT USAGE ON SCHEMA public
    TO research_writer, control_reader, market_data_writer, execution_writer,
       backtest_writer, audit_writer;

-- research_writer resolves canonical_symbol -> instrument_id (and back) on every
-- upsert/list/context read, so it needs read-only access to the shared instrument
-- reference table even though it never writes to it.
GRANT SELECT ON
    instruments
TO research_writer;

GRANT SELECT, INSERT, UPDATE ON
    research_sources,
    research_documents,
    research_document_occurrences,
    document_assets,
    document_relations,
    research_analyses
TO research_writer;

-- Every upsert replaces a document's asset links with DELETE + re-INSERT
-- (src/research/postgres_store.py::_replace_assets), so research_writer needs
-- DELETE on document_assets specifically; the other research tables are never
-- deleted from by application code.
GRANT DELETE ON document_assets TO research_writer;

GRANT SELECT ON
    assets,
    instruments,
    instrument_symbols,
    exchanges,
    exchange_accounts,
    research_sources,
    research_documents,
    research_document_occurrences,
    document_assets,
    document_relations,
    research_analyses,
    market_data_sources,
    ohlcv_candles,
    order_book_snapshots,
    trades,
    strategies,
    strategy_versions,
    risk_limits,
    portfolios,
    balances,
    positions,
    signals,
    orders,
    order_events,
    executions,
    risk_events,
    backtest_runs,
    backtest_trades,
    paper_trading_runs,
    agent_runs,
    audit_log,
    agent_actions,
    system_events,
    human_approvals,
    alerts
TO control_reader;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO research_writer;

-- market_data_writer resolves canonical_symbol -> instrument_id and source name ->
-- source_id on every upsert/load (src/data/postgres_store.py::PostgresCandleStore), so
-- it needs read-only access to the shared reference tables even though it never
-- writes to them directly (market_data_sources rows are seeded by the migration
-- owner via scripts/db/seed.py, not by the application).
GRANT SELECT ON
    exchanges,
    instruments,
    instrument_symbols,
    market_data_sources
TO market_data_writer;

-- UPSERT (ON CONFLICT ... DO UPDATE) needs INSERT and UPDATE; candles are never
-- deleted by application code (docs/database-design.md §15 — append-mostly time
-- series, corrections happen in place). No DELETE grant.
GRANT SELECT, INSERT, UPDATE ON ohlcv_candles TO market_data_writer;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO market_data_writer;

-- execution_writer (paper/live engine process, docs/database-design.md Phase 3+4).
-- Reference tables it resolves ids from on every write but never writes to itself.
GRANT SELECT ON
    instruments,
    assets,
    exchanges,
    exchange_accounts,
    strategies,
    strategy_versions,
    risk_limits,
    portfolios
TO execution_writer;

-- Mutable current-state tables: engine UPSERTs balances/positions and updates
-- orders.status as fills arrive (docs/database-design.md §8.4-8.5). No DELETE —
-- closed positions/rejected orders stay as rows, never removed.
GRANT SELECT, INSERT, UPDATE ON balances, positions, orders TO execution_writer;

-- Append-only jurnals: order_events, executions, signals, risk_events are never
-- updated or deleted by application code once written (docs/database-design.md
-- §13/§15 — same "no UPDATE/DELETE" posture as audit_log, enforced at the role
-- level here rather than by convention alone).
GRANT SELECT, INSERT ON order_events, executions, signals, risk_events TO execution_writer;

-- Paper sessions upsert their own long-lived paper_trading_runs row (one per
-- portfolio, docs/database-design.md §8.6 / 0004_backtest_paper_runs.py deviations
-- note) — the engine process already holds EXECUTION_DATABASE_URL, so this reuses
-- execution_writer rather than introducing a third writer role. No DELETE.
GRANT SELECT, INSERT, UPDATE ON paper_trading_runs TO execution_writer;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO execution_writer;

-- backtest_writer (control process, src/control/backtest_jobs.py +
-- scripts/backtest/run_backtest.py CLI suite). Reference tables it resolves ids
-- from but never writes to.
GRANT SELECT ON
    instruments,
    strategy_versions,
    market_data_sources
TO backtest_writer;

-- backtest_runs transitions status queued -> running -> completed/failed
-- (docs/database-design.md §8.6 says immutable once status='completed'; the
-- application enforces that by only ever UPDATEing a row it just INSERTed as
-- queued/running, never a completed one — the role grant itself cannot express
-- "no further UPDATE past this status value").
GRANT SELECT, INSERT, UPDATE ON backtest_runs TO backtest_writer;

-- backtest_trades is append-only, same posture as order_events/executions above.
GRANT SELECT, INSERT ON backtest_trades TO backtest_writer;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO backtest_writer;

-- audit_writer (control + engine, docs/database-design.md §8.10 / Phase 7). Both
-- processes connect with this single role's credentials — see the CREATE ROLE
-- comment above for why this is not split like every other domain.
-- Reference table it resolves order_id from when linking a decided approval to
-- the order it produced (best-effort; stays NULL if unresolved — never guessed).
GRANT SELECT ON orders, users TO audit_writer;

-- audit_log is append-only by design (docs/database-design.md §8.10: "Fără
-- UPDATE/DELETE la nivel de rol DB, nu doar de convenție de cod"). INSERT only —
-- UPDATE/DELETE are explicitly revoked below (migration 0005) even though they
-- are never granted here either; the REVOKE is the actual enforcement in case a
-- future GRANT ALL-style change is applied by mistake.
GRANT SELECT, INSERT ON audit_log TO audit_writer;

-- human_approvals: INSERT at request time (engine), UPDATE at decision time
-- (control) and when linking order_id after a later order_submitted (engine). No
-- DELETE — a decision is never retracted, only superseded by a fresh approval
-- under a new correlation_id.
GRANT SELECT, INSERT, UPDATE ON human_approvals TO audit_writer;

-- agent_runs: INSERT at engine process start, UPDATE (stopped_at/stop_reason) at
-- graceful shutdown. No DELETE — a run's row is permanent history.
GRANT SELECT, INSERT, UPDATE ON agent_runs TO audit_writer;

-- system_events: append-mostly operational log, same posture as order_events.
GRANT SELECT, INSERT ON system_events TO audit_writer;

-- alerts: INSERT on first sighting of an unresolved condition, UPDATE for
-- operator ack/resolve. No DELETE — resolved alerts stay as history.
GRANT SELECT, INSERT, UPDATE ON alerts TO audit_writer;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO audit_writer;

-- Enforced at the role level, not just by omitting the grant above (mirrors the
-- design's explicit "not just code convention" intent for audit_log). REVOKE
-- targets audit_writer and control_reader specifically, plus PUBLIC as a floor —
-- the design doc says "FROM app_writer", a placeholder from the original
-- single-role draft; see migration 0005's docstring for the same note.
REVOKE UPDATE, DELETE ON audit_log FROM audit_writer, control_reader, PUBLIC;
