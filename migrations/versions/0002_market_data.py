"""Create TimescaleDB extension and market data schema (OHLCV candles + empty L2/tape).

Revision ID: 0002_market_data
Revises: 0001_foundation_research
Create Date: 2026-09-21
"""

from alembic import op

revision = "0002_market_data"
down_revision = "0001_foundation_research"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
    op.execute(
        """
        CREATE TABLE market_data_sources (
            source_id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            exchange_id INT REFERENCES exchanges(exchange_id),
            kind TEXT NOT NULL CHECK (
                kind IN ('rest_public', 'rest_authenticated', 'websocket', 'vendor_bulk')
            ),
            requires_auth BOOLEAN NOT NULL DEFAULT false,
            rate_limit_per_min INT,
            active BOOLEAN NOT NULL DEFAULT true
        );

        CREATE TABLE ohlcv_candles (
            source_id INT NOT NULL REFERENCES market_data_sources(source_id),
            instrument_id UUID NOT NULL REFERENCES instruments(instrument_id),
            timeframe TEXT NOT NULL,
            open_time TIMESTAMPTZ NOT NULL,
            open NUMERIC NOT NULL,
            high NUMERIC NOT NULL,
            low NUMERIC NOT NULL,
            close NUMERIC NOT NULL,
            volume NUMERIC NOT NULL,
            trade_count INT,
            is_final BOOLEAN NOT NULL DEFAULT true,
            ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (source_id, instrument_id, timeframe, open_time)
        );
        SELECT create_hypertable(
            'ohlcv_candles', 'open_time', chunk_time_interval => INTERVAL '7 days'
        );
        CREATE INDEX idx_candles_instrument_tf_time
            ON ohlcv_candles (instrument_id, timeframe, open_time DESC);

        -- Projected, not ingested yet (docs/database-design.md §8.3, §22). Timescale
        -- requires every unique index on a hypertable to include the partitioning
        -- column, so the natural keys below carry the time column explicitly
        -- (deviation from the design doc's plain `id BIGSERIAL PRIMARY KEY` /
        -- `UNIQUE (source_id, instrument_id, venue_trade_id)`, documented in the
        -- market data cutover plan).
        CREATE TABLE order_book_snapshots (
            id BIGSERIAL NOT NULL,
            source_id INT NOT NULL REFERENCES market_data_sources(source_id),
            instrument_id UUID NOT NULL REFERENCES instruments(instrument_id),
            captured_at TIMESTAMPTZ NOT NULL,
            best_bid NUMERIC,
            best_ask NUMERIC,
            bids JSONB NOT NULL,
            asks JSONB NOT NULL,
            sequence_number BIGINT,
            PRIMARY KEY (id, captured_at)
        );
        SELECT create_hypertable(
            'order_book_snapshots', 'captured_at', chunk_time_interval => INTERVAL '1 day'
        );

        CREATE TABLE trades (
            id BIGSERIAL NOT NULL,
            source_id INT NOT NULL REFERENCES market_data_sources(source_id),
            instrument_id UUID NOT NULL REFERENCES instruments(instrument_id),
            traded_at TIMESTAMPTZ NOT NULL,
            price NUMERIC NOT NULL,
            quantity NUMERIC NOT NULL,
            side TEXT CHECK (side IN ('buy', 'sell')),
            venue_trade_id TEXT,
            PRIMARY KEY (id, traded_at),
            UNIQUE (source_id, instrument_id, venue_trade_id, traded_at)
        );
        SELECT create_hypertable(
            'trades', 'traded_at', chunk_time_interval => INTERVAL '1 day'
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE trades;
        DROP TABLE order_book_snapshots;
        DROP TABLE ohlcv_candles;
        DROP TABLE market_data_sources;
        """
    )
