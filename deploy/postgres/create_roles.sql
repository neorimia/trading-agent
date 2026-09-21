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
END
$$;

ALTER ROLE research_writer PASSWORD :'research_password';
ALTER ROLE control_reader PASSWORD :'control_password';

GRANT CONNECT ON DATABASE :"database_name" TO research_writer, control_reader;
GRANT USAGE ON SCHEMA public TO research_writer, control_reader;

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
    research_analyses
TO control_reader;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO research_writer;
