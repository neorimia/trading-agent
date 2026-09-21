# Database domain cutover playbook

The research cutover is the reference implementation. Every remaining persistence
domain uses the same reversible sequence; no domain is switched merely because its
tables exist.

## Required gates for every domain

1. Apply reviewed Alembic migrations from zero in CI.
2. Seed immutable reference data before importing dependent rows.
3. Import from a frozen copy of the legacy source with an idempotent command.
4. Emit a JSON reconciliation report containing source/destination counts, rejected
   rows, natural-key conflicts, and sampled hashes.
5. Run the old and new repository contract suites against identical fixtures.
6. Stop the domain's writers, take a final legacy snapshot, rerun the importer, and
   require a clean reconciliation report.
7. Switch the backend setting, verify readiness and domain smoke tests, then resume
   writers.
8. Roll back by stopping writers and restoring the old backend setting. Legacy data
   stays immutable until a successful PostgreSQL restore drill and observation window.

Dual writes are allowed only when a domain cannot tolerate a short writer pause. They
must be transactional on the PostgreSQL side and include an explicit divergence alarm;
silent best-effort dual writes are prohibited.

## Domain order and ownership

### 1. Market data

- Source: `.cache/*.json`, with network re-backfill preferred when provenance is
  incomplete.
- Target: `market_data_sources`, `ohlcv_candles`.
- Enable TimescaleDB in this slice, not in the research/foundation migration.
- Gate: repeated backfill produces the same primary-key count and dataset hash.

### 2. Portfolio and execution

- Sources: `runtime/paper*/control/*.json` and
  `runtime/paper*/execution/idempotency.sqlite`.
- Targets: portfolios, balances, positions, orders, order events, executions.
- Gate: reconcile audit fills, local positions, broker snapshots, and idempotency
  reservations. Any mismatch is quarantined rather than guessed.
- Live trading remains blocked until restart reconciliation closes the
  `reserve` to `store_result` crash window.

### 3. Strategies, risk, and signals

- Sources: `config/strategies.yaml`, `config/risk_limits.yaml`, and correlated audit
  events.
- Targets: strategies, strategy versions, versioned risk limits/events, signals.
- Gate: every imported decision resolves to the exact strategy/risk version active at
  its timestamp; unresolved history is reported.

### 4. Backtest and paper runs

- Sources: `backtests/reports/**/manifest.json`, trade reports, and each
  `runtime/paper*` directory.
- Targets: backtest runs/trades and paper-trading runs.
- Gate: run IDs, dataset hashes, seeds, strategy versions, metrics, and on-disk report
  pointers reproduce the legacy manifests.

### 5. Audit, approvals, and system events

- Sources: `audit.sqlite`, approval request/decision JSON files, heartbeat and
  reconciliation history that has business value.
- Targets: append-only audit, human approvals, agent runs, alerts, system events.
- Cut this domain over last.
- Gate: correlation chains remain complete, pagination is stable, append-only grants
  are enforced, and no approval decision is orphaned.

## Operations after all paper domains are cut over

- Keep halt flags, PID files, and immutable research/backtest blobs on disk.
- Continue daily logical dumps plus restic and periodic restore drills.
- Add WAL archiving and point-in-time recovery only before 24/7 live trading.
- Remove a legacy adapter/path only in a separate cleanup change after its rollback
  window has expired.
