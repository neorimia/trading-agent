"""Create portfolio/execution and strategy/risk/signal schema (design Phases 3+4).

Revision ID: 0003_execution_risk
Revises: 0002_market_data
Create Date: 2026-09-21

Deviations from docs/database-design.md §8 (documented per docs/database-cutover-
playbook.md convention, same as 0002's Timescale unique-key note):

- `strategies.kind` / `signals.source` include every kind implemented by
  `src/engine/strategy_registry.py` (`ALL_KINDS`): `ema_cross`, `donchian_breakout`,
  `rsi_mean_reversion`, `llm` (design only listed `ema_cross`/`llm`); `signals.source`
  also keeps `none` (no strategy fired).
- `risk_limits` adds the nullable columns already live in `config/risk_limits.yaml`
  and `src/risk/config_schema.py::RiskLimits` (`max_risk_per_trade`,
  `min_reward_risk_ratio`, `max_spread_bps`, `min_bar_volume`,
  `max_correlated_exposure`) so a versioned row carries every limit that actually
  ran, not just the MVP subset from the design doc.
- `orders.status` adds `unknown` and `timeout` from `src/execution/types.py`
  (`OrderStatus`) — real halt-triggering broker outcomes that must not be collapsed
  into `submitted` or invented as `rejected`. `filled` from that same enum is stored
  as `executed` (the design's terminal-success status name).
- `risk_events.event_type` includes `reconciliation_mismatch` (docs/database-
  design.md §13 already requires this event type to exist).
- `orders.client_order_id` stays nullable+UNIQUE (not NOT NULL) so a future audit-
  only import row (no idempotency reservation on record) can still be represented.
"""

from alembic import op

revision = "0003_execution_risk"
down_revision = "0002_market_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE strategies (
            strategy_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (
                kind IN ('ema_cross', 'donchian_breakout', 'rsi_mean_reversion', 'llm')
            ),
            enabled BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE strategy_versions (
            strategy_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            strategy_id TEXT NOT NULL REFERENCES strategies(strategy_id),
            version INT NOT NULL,
            params JSONB NOT NULL,
            change_note TEXT,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_by UUID REFERENCES users(user_id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (strategy_id, version)
        );

        CREATE TABLE risk_limits (
            risk_limits_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            effective_from TIMESTAMPTZ NOT NULL,
            effective_to TIMESTAMPTZ,
            max_notional_per_order NUMERIC NOT NULL,
            max_exposure_per_instrument NUMERIC NOT NULL,
            max_exposure_per_asset_class NUMERIC NOT NULL,
            max_daily_loss NUMERIC NOT NULL,
            max_drawdown NUMERIC NOT NULL,
            max_orders_per_day INT NOT NULL,
            max_consecutive_errors INT NOT NULL,
            max_consecutive_losses INT NOT NULL,
            halt_on_unknown_order_result BOOLEAN NOT NULL,
            max_risk_per_trade NUMERIC,
            min_reward_risk_ratio NUMERIC,
            max_spread_bps NUMERIC,
            min_bar_volume NUMERIC,
            max_correlated_exposure NUMERIC,
            changed_by TEXT NOT NULL,
            confirmation_token_used TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX uq_risk_limits_one_open
            ON risk_limits (effective_to) WHERE effective_to IS NULL;

        CREATE TABLE portfolios (
            portfolio_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL UNIQUE,
            trading_mode TEXT NOT NULL CHECK (trading_mode IN ('paper', 'live')),
            exchange_account_id UUID REFERENCES exchange_accounts(exchange_account_id),
            base_currency TEXT NOT NULL DEFAULT 'USD',
            starting_cash NUMERIC NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE balances (
            portfolio_id UUID NOT NULL REFERENCES portfolios(portfolio_id),
            asset_id INT NOT NULL REFERENCES assets(asset_id),
            source TEXT NOT NULL CHECK (source IN ('local_ledger', 'exchange_reported')),
            quantity NUMERIC NOT NULL,
            reserved_quantity NUMERIC NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (portfolio_id, asset_id, source)
        );

        CREATE TABLE positions (
            position_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            portfolio_id UUID NOT NULL REFERENCES portfolios(portfolio_id),
            instrument_id UUID NOT NULL REFERENCES instruments(instrument_id),
            quantity NUMERIC NOT NULL,
            avg_entry_price NUMERIC,
            last_price NUMERIC,
            unrealized_pnl NUMERIC,
            stop_loss NUMERIC,
            take_profit NUMERIC,
            stop_source TEXT NOT NULL DEFAULT 'engine_default_2pct',
            opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            closed_at TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX uq_positions_open_per_instrument
            ON positions (portfolio_id, instrument_id) WHERE closed_at IS NULL;
        CREATE INDEX idx_positions_portfolio_closed ON positions (portfolio_id, closed_at);

        CREATE TABLE signals (
            signal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            instrument_id UUID NOT NULL REFERENCES instruments(instrument_id),
            strategy_version_id UUID REFERENCES strategy_versions(strategy_version_id),
            source TEXT NOT NULL CHECK (
                source IN (
                    'ema_cross', 'donchian_breakout', 'rsi_mean_reversion', 'llm', 'none'
                )
            ),
            direction TEXT,
            confidence NUMERIC CHECK (confidence BETWEEN 0 AND 1 OR confidence IS NULL),
            rationale TEXT,
            sources JSONB NOT NULL DEFAULT '[]'::jsonb,
            is_proposal BOOLEAN NOT NULL DEFAULT true,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_signals_instrument_time ON signals (instrument_id, generated_at DESC);

        CREATE TABLE orders (
            order_id UUID PRIMARY KEY,
            client_order_id UUID UNIQUE,
            portfolio_id UUID NOT NULL REFERENCES portfolios(portfolio_id),
            instrument_id UUID NOT NULL REFERENCES instruments(instrument_id),
            strategy_version_id UUID REFERENCES strategy_versions(strategy_version_id),
            signal_id UUID REFERENCES signals(signal_id),
            risk_limits_version_id UUID REFERENCES risk_limits(risk_limits_version_id),
            side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
            order_type TEXT NOT NULL DEFAULT 'market' CHECK (order_type IN ('market', 'limit')),
            requested_quantity NUMERIC NOT NULL,
            limit_price NUMERIC,
            trading_mode TEXT NOT NULL CHECK (trading_mode IN ('paper', 'live')),
            status TEXT NOT NULL CHECK (
                status IN (
                    'proposed', 'approved', 'rejected', 'submitted', 'partially_filled',
                    'executed', 'cancelled', 'unknown', 'timeout'
                )
            ),
            reason TEXT,
            requested_at TIMESTAMPTZ NOT NULL,
            decided_at TIMESTAMPTZ,
            submitted_at TIMESTAMPTZ,
            closed_at TIMESTAMPTZ
        );
        CREATE INDEX idx_orders_portfolio_status
            ON orders (portfolio_id, status, requested_at DESC);
        CREATE INDEX idx_orders_instrument_time ON orders (instrument_id, requested_at DESC);

        CREATE TABLE order_events (
            id BIGSERIAL PRIMARY KEY,
            order_id UUID NOT NULL REFERENCES orders(order_id),
            event_type TEXT NOT NULL CHECK (
                event_type IN (
                    'proposed', 'risk_checked', 'approval_requested', 'approved', 'rejected',
                    'submitted', 'ack', 'partial_fill', 'filled', 'cancel_requested',
                    'cancelled', 'error'
                )
            ),
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            payload JSONB NOT NULL,
            correlation_id UUID NOT NULL
        );
        CREATE INDEX idx_order_events_order ON order_events (order_id, occurred_at);

        CREATE TABLE executions (
            execution_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id UUID NOT NULL REFERENCES orders(order_id),
            instrument_id UUID NOT NULL REFERENCES instruments(instrument_id),
            trading_mode TEXT NOT NULL CHECK (trading_mode IN ('paper', 'live')),
            fill_price NUMERIC NOT NULL,
            fill_quantity NUMERIC NOT NULL,
            fee NUMERIC NOT NULL DEFAULT 0,
            fee_asset TEXT,
            slippage NUMERIC,
            venue_execution_id TEXT UNIQUE,
            executed_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_executions_order ON executions (order_id);

        CREATE TABLE risk_events (
            id BIGSERIAL PRIMARY KEY,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            order_id UUID REFERENCES orders(order_id),
            event_type TEXT NOT NULL CHECK (
                event_type IN (
                    'order_accepted', 'order_rejected', 'circuit_breaker_tripped',
                    'max_drawdown_halt', 'max_daily_loss_halt', 'kill_switch',
                    'manual_halt', 'reconciliation_mismatch'
                )
            ),
            reason TEXT,
            portfolio_state_snapshot JSONB NOT NULL,
            risk_limits_version_id UUID NOT NULL REFERENCES risk_limits(risk_limits_version_id),
            correlation_id UUID NOT NULL
        );
        CREATE INDEX idx_risk_events_order ON risk_events (order_id);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE risk_events;
        DROP TABLE executions;
        DROP TABLE order_events;
        DROP TABLE orders;
        DROP TABLE signals;
        DROP TABLE positions;
        DROP TABLE balances;
        DROP TABLE portfolios;
        DROP TABLE risk_limits;
        DROP TABLE strategy_versions;
        DROP TABLE strategies;
        """
    )
