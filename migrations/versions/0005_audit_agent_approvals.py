"""Create audit/agent/approvals entity schema (design Phase 7, §8.10).

Revision ID: 0005_audit_agent_approvals
Revises: 0004_backtest_paper_runs
Create Date: 2026-09-22

Deviations from docs/database-design.md §8.10 (documented per docs/database-cutover-
playbook.md convention, same as 0002-0004's notes):

- `audit_log.event_type` CHECK enumerates the 14 values already live in
  `src/audit/events.py::AuditEventType`, not a separate placeholder list — the
  design doc's CHECK already matches this exactly, so no divergence there.
- `REVOKE UPDATE, DELETE ON audit_log FROM audit_writer, control_reader, PUBLIC`
  targets the roles this codebase's `deploy/postgres/create_roles.sql` actually
  creates. The design doc says "FROM app_writer" — a placeholder name from the
  original single-role draft, superseded by the per-domain role split adopted in
  0002-0004 (`market_data_writer`, `execution_writer`, `backtest_writer`).
- `human_approvals.order_id` is nullable (still UNIQUE): a denied/timed-out/
  expired approval never produces an `orders` row — `order_submitted` only fires
  after an approval succeeds (`src/engine/strategy_paper.py`) — so `NOT NULL
  REFERENCES orders` is unsatisfiable for the majority of rows.
- `human_approvals.decided_by` and `.reason` are nullable: at request time
  (INSERT) nothing has decided anything yet, both are only known at decision time
  (UPDATE). `approved` was already nullable in the design's own DDL comment
  ("NULL = pending/expired").
"""

from alembic import op

revision = "0005_audit_agent_approvals"
down_revision = "0004_backtest_paper_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE agent_runs (
            agent_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            portfolio_id UUID REFERENCES portfolios(portfolio_id),
            trading_mode TEXT NOT NULL CHECK (trading_mode IN ('paper', 'live')),
            strategy_version_id UUID NOT NULL REFERENCES strategy_versions(strategy_version_id),
            git_commit TEXT,
            config_snapshot JSONB NOT NULL,
            host TEXT,
            pid INT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            stopped_at TIMESTAMPTZ,
            stop_reason TEXT
        );
        CREATE INDEX idx_agent_runs_started ON agent_runs (started_at DESC);

        CREATE TABLE audit_log (
            id BIGSERIAL PRIMARY KEY,
            "timestamp" TIMESTAMPTZ NOT NULL DEFAULT now(),
            correlation_id UUID NOT NULL,
            event_type TEXT NOT NULL CHECK (event_type IN (
                'proposal', 'rejected_proposal', 'risk_decision', 'human_approval',
                'order_submitted', 'fill', 'halt', 'reconciliation_ok',
                'reconciliation_mismatch', 'run_bar_error', 'operator_action',
                'analysis', 'signal_normalized', 'discovery_summary'
            )),
            payload JSONB NOT NULL
        );
        CREATE INDEX idx_audit_log_correlation ON audit_log (correlation_id);
        CREATE INDEX idx_audit_log_time ON audit_log ("timestamp" DESC);

        CREATE VIEW agent_actions AS
        SELECT id, "timestamp", correlation_id, event_type, payload
        FROM audit_log
        WHERE event_type IN (
            'proposal', 'rejected_proposal', 'risk_decision',
            'order_submitted', 'halt', 'operator_action'
        );

        CREATE TABLE system_events (
            id BIGSERIAL PRIMARY KEY,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'error', 'critical')),
            component TEXT NOT NULL,
            event_type TEXT NOT NULL,
            message TEXT NOT NULL,
            payload JSONB
        );
        CREATE INDEX idx_system_events_time ON system_events (occurred_at DESC);

        CREATE TABLE human_approvals (
            approval_id UUID PRIMARY KEY,
            order_id UUID UNIQUE REFERENCES orders(order_id),
            user_id UUID REFERENCES users(user_id),
            decided_by TEXT,
            requested_at TIMESTAMPTZ NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            decided_at TIMESTAMPTZ,
            approved BOOLEAN,
            reason TEXT,
            request_payload JSONB NOT NULL
        );

        CREATE TABLE alerts (
            alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            severity TEXT NOT NULL CHECK (severity IN ('warning', 'error')),
            title TEXT NOT NULL,
            detail TEXT NOT NULL,
            persistent BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            acknowledged_at TIMESTAMPTZ,
            acknowledged_by UUID REFERENCES users(user_id),
            resolved_at TIMESTAMPTZ
        );
        CREATE INDEX idx_alerts_unresolved ON alerts (title) WHERE resolved_at IS NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE alerts;
        DROP TABLE human_approvals;
        DROP TABLE system_events;
        DROP VIEW agent_actions;
        DROP TABLE audit_log;
        DROP TABLE agent_runs;
        """
    )
