"""Create PostgreSQL foundation and research schema.

Revision ID: 0001_foundation_research
Revises:
Create Date: 2026-09-21
"""

from alembic import op

revision = "0001_foundation_research"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE users (
            user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            username TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL CHECK (role IN ('operator', 'observer')),
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE exchanges (
            exchange_id SERIAL PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (
                kind IN ('crypto_exchange', 'stock_exchange', 'broker')
            ),
            supports_execution BOOLEAN NOT NULL DEFAULT false,
            supports_historical_data BOOLEAN NOT NULL DEFAULT false,
            api_base_url TEXT,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE exchange_accounts (
            exchange_account_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            exchange_id INT NOT NULL REFERENCES exchanges(exchange_id),
            label TEXT NOT NULL,
            trading_mode TEXT NOT NULL CHECK (trading_mode IN ('paper', 'live')),
            scope TEXT NOT NULL CHECK (scope IN ('spot', 'futures', 'futures_demo')),
            subaccount BOOLEAN NOT NULL DEFAULT false,
            ip_whitelist_configured BOOLEAN NOT NULL DEFAULT false,
            withdraw_enabled BOOLEAN NOT NULL DEFAULT false,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (exchange_id, trading_mode, scope, label)
        );

        CREATE TABLE api_credentials_metadata (
            credential_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            exchange_account_id UUID NOT NULL REFERENCES exchange_accounts(exchange_account_id),
            env_var_name TEXT NOT NULL,
            key_scope TEXT NOT NULL CHECK (
                key_scope IN ('read_only', 'paper_trading', 'live_trading')
            ),
            last_rotated_at TIMESTAMPTZ,
            last_verified_present_at TIMESTAMPTZ,
            created_by UUID REFERENCES users(user_id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at TIMESTAMPTZ
        );

        CREATE TABLE secret_access_log (
            id BIGSERIAL PRIMARY KEY,
            credential_id UUID NOT NULL REFERENCES api_credentials_metadata(credential_id),
            accessed_by TEXT NOT NULL,
            accessed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            purpose TEXT NOT NULL
        );

        CREATE TABLE assets (
            asset_id SERIAL PRIMARY KEY,
            symbol TEXT NOT NULL UNIQUE,
            asset_class TEXT NOT NULL CHECK (
                asset_class IN ('crypto', 'equity', 'fx', 'cash')
            ),
            name TEXT NOT NULL,
            decimals SMALLINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE instruments (
            instrument_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            base_asset_id INT NOT NULL REFERENCES assets(asset_id),
            quote_asset_id INT REFERENCES assets(asset_id),
            asset_class TEXT NOT NULL CHECK (asset_class IN ('crypto', 'equity', 'fx')),
            canonical_symbol TEXT NOT NULL UNIQUE,
            min_notional NUMERIC NOT NULL DEFAULT 1,
            lot_size NUMERIC NOT NULL DEFAULT 1,
            tick_size NUMERIC NOT NULL DEFAULT 0.01,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE instrument_symbols (
            instrument_symbol_id SERIAL PRIMARY KEY,
            instrument_id UUID NOT NULL REFERENCES instruments(instrument_id),
            exchange_id INT NOT NULL REFERENCES exchanges(exchange_id),
            venue_symbol TEXT NOT NULL,
            role TEXT NOT NULL CHECK (
                role IN ('execution', 'historical_backfill', 'both')
            ),
            is_primary BOOLEAN NOT NULL DEFAULT true,
            UNIQUE (instrument_id, exchange_id, role)
        );
        CREATE INDEX idx_instrument_symbols_venue
            ON instrument_symbols(exchange_id, venue_symbol);

        CREATE TABLE research_sources (
            source_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (
                kind IN ('rss', 'api', 'html_crawler', 'browser_automation')
            ),
            base_url TEXT NOT NULL,
            credibility_score NUMERIC NOT NULL CHECK (
                credibility_score BETWEEN 0 AND 1
            ),
            robots_txt_status TEXT NOT NULL CHECK (
                robots_txt_status IN (
                    'allowed', 'disallowed', 'not_applicable_api', 'pending'
                )
            ),
            tos_reviewed_at TIMESTAMPTZ,
            active BOOLEAN NOT NULL DEFAULT true,
            rate_limit_per_min INT CHECK (
                rate_limit_per_min > 0 OR rate_limit_per_min IS NULL
            ),
            min_request_interval_s NUMERIC CHECK (
                min_request_interval_s > 0 OR min_request_interval_s IS NULL
            ),
            review_status TEXT NOT NULL CHECK (
                review_status IN (
                    'pending', 'pending_manual_tos_review',
                    'docs_reviewed_terms_pending', 'reviewed',
                    'reviewed_with_dynamic_limit'
                )
            ),
            docs_url TEXT,
            terms_url TEXT,
            robots_url TEXT,
            rate_limit_source TEXT,
            rate_limit_notes TEXT,
            last_verified_at TIMESTAMPTZ,
            attribution_required BOOLEAN NOT NULL DEFAULT false,
            redistribution_allowed TEXT NOT NULL DEFAULT 'unknown' CHECK (
                redistribution_allowed IN ('yes', 'no', 'unknown')
            ),
            retention_policy TEXT NOT NULL DEFAULT 'metadata_and_summary_only',
            notes JSONB NOT NULL DEFAULT '[]'::jsonb,
            CHECK (jsonb_typeof(notes) = 'array')
        );

        CREATE TABLE research_documents (
            doc_id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            source_id TEXT NOT NULL REFERENCES research_sources(source_id),
            author TEXT,
            published_at TIMESTAMPTZ,
            fetched_at TIMESTAMPTZ NOT NULL,
            event_date TIMESTAMPTZ,
            category TEXT NOT NULL CHECK (
                category IN (
                    'news', 'earnings', 'filing', 'macro_indicator',
                    'market_analysis', 'sentiment', 'geopolitical',
                    'protocol_upgrade', 'token_unlock', 'governance',
                    'listing', 'onchain_alert', 'funding_regime', 'regulatory'
                )
            ),
            language TEXT NOT NULL DEFAULT 'en',
            extracted_text TEXT NOT NULL,
            content_hash TEXT NOT NULL UNIQUE,
            raw_payload_ref TEXT,
            summary TEXT,
            sentiment_score NUMERIC CHECK (
                sentiment_score BETWEEN -1 AND 1 OR sentiment_score IS NULL
            ),
            impact_magnitude TEXT CHECK (
                impact_magnitude IN ('low', 'medium', 'high')
                OR impact_magnitude IS NULL
            ),
            impact_direction TEXT CHECK (
                impact_direction IN ('bullish', 'bearish', 'neutral', 'unclear')
                OR impact_direction IS NULL
            ),
            confidence_score NUMERIC NOT NULL DEFAULT 0 CHECK (
                confidence_score BETWEEN 0 AND 1
            ),
            data_quality_score NUMERIC CHECK (
                data_quality_score BETWEEN 0 AND 1 OR data_quality_score IS NULL
            ),
            last_verified_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX idx_research_documents_fetched_at
            ON research_documents(fetched_at DESC);
        CREATE INDEX idx_research_documents_event_date
            ON research_documents(event_date);

        CREATE TABLE research_document_occurrences (
            occurrence_id TEXT PRIMARY KEY,
            canonical_doc_id TEXT NOT NULL REFERENCES research_documents(doc_id),
            url TEXT,
            source_id TEXT REFERENCES research_sources(source_id),
            fetched_at TIMESTAMPTZ,
            raw_payload_ref TEXT,
            legacy_metadata_incomplete BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (source_id, url, fetched_at),
            CHECK (
                legacy_metadata_incomplete
                OR (url IS NOT NULL AND source_id IS NOT NULL AND fetched_at IS NOT NULL)
            )
        );
        CREATE INDEX idx_research_occurrences_canonical
            ON research_document_occurrences(canonical_doc_id, fetched_at DESC);

        CREATE TABLE document_assets (
            doc_id TEXT NOT NULL REFERENCES research_documents(doc_id) ON DELETE CASCADE,
            instrument_id UUID NOT NULL REFERENCES instruments(instrument_id),
            PRIMARY KEY (doc_id, instrument_id)
        );

        CREATE TABLE document_relations (
            doc_id TEXT NOT NULL REFERENCES research_documents(doc_id) ON DELETE CASCADE,
            related_doc_id TEXT NOT NULL REFERENCES research_documents(doc_id) ON DELETE CASCADE,
            relation_type TEXT NOT NULL CHECK (
                relation_type IN (
                    'confirms', 'contradicts', 'retracted_by', 'follow_up_of'
                )
            ),
            PRIMARY KEY (doc_id, related_doc_id, relation_type),
            CHECK (doc_id <> related_doc_id)
        );

        CREATE TABLE research_analyses (
            analysis_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            instrument_id UUID NOT NULL REFERENCES instruments(instrument_id),
            strategy_version_id UUID,
            analysis_type TEXT NOT NULL CHECK (
                analysis_type IN (
                    'priced_in', 'technical', 'news_impact', 'stress',
                    'backtest', 'trade_review', 'daily_plan', 'discovery'
                )
            ),
            requested_by TEXT NOT NULL CHECK (requested_by IN ('agent', 'operator')),
            model_name TEXT NOT NULL,
            prompt_hash TEXT NOT NULL,
            prompt_version TEXT,
            facts_bundle_hash TEXT NOT NULL,
            temperature NUMERIC NOT NULL,
            schema_version TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            confidence_score NUMERIC NOT NULL CHECK (
                confidence_score BETWEEN 0 AND 1
            ),
            data_quality_score NUMERIC NOT NULL CHECK (
                data_quality_score BETWEEN 0 AND 1
            ),
            recommended_action TEXT NOT NULL,
            action_type TEXT NOT NULL DEFAULT 'research_only',
            required_human_approval BOOLEAN NOT NULL DEFAULT true,
            body JSONB NOT NULL,
            rejected BOOLEAN NOT NULL DEFAULT false,
            reject_reason TEXT,
            raw_output TEXT,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expiry_time TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX idx_research_analyses_instrument_time
            ON research_analyses(instrument_id, generated_at DESC);
        CREATE INDEX idx_research_analyses_model
            ON research_analyses(model_name, generated_at DESC);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE research_analyses;
        DROP TABLE document_relations;
        DROP TABLE document_assets;
        DROP TABLE research_document_occurrences;
        DROP TABLE research_documents;
        DROP TABLE research_sources;
        DROP TABLE instrument_symbols;
        DROP TABLE instruments;
        DROP TABLE assets;
        DROP TABLE secret_access_log;
        DROP TABLE api_credentials_metadata;
        DROP TABLE exchange_accounts;
        DROP TABLE exchanges;
        DROP TABLE users;
        """
    )
