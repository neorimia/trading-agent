\set ON_ERROR_STOP on
\if :{?database_name}
\else
\set database_name trading_research
\endif

-- Supply passwords with psql variables:
-- psql ... -v research_password='...' -v control_password='...' -f create_roles.sql
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
END
$$;

ALTER ROLE research_writer PASSWORD :'research_password';
ALTER ROLE control_reader PASSWORD :'control_password';
ALTER ROLE market_data_writer PASSWORD :'market_data_password';

GRANT CONNECT ON DATABASE :"database_name" TO research_writer, control_reader, market_data_writer;
GRANT USAGE ON SCHEMA public TO research_writer, control_reader, market_data_writer;

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
    research_sources,
    research_documents,
    research_document_occurrences,
    document_assets,
    document_relations,
    research_analyses,
    market_data_sources,
    ohlcv_candles,
    order_book_snapshots,
    trades
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
