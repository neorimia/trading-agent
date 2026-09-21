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
- **Status: implemented.** `MARKET_DATA_STORE_BACKEND=files|postgres` (default
  `files`, `MARKET_DATA_DATABASE_URL` for role `market_data_writer`) —
  `src/data/market_data_repository.py::open_market_data_cache`. Importer:
  `scripts/db/import_market_data.py --source KRAKEN|BINANCE` (network re-backfill by
  default; `--from-cache` reads a frozen `.cache/market_data/` window and always
  marks the report `provenance_incomplete: true`, since JSON cache files do not
  record which vendor produced them). `Bar.timestamp` (close-time) maps to
  `open_time` (period start) via `close_time = open_time + timeframe_delta - 1s` —
  the convention already shared by Kraken/Binance/the CSV fixture
  (`src/data/postgres_store.py`). Local/CI Postgres is TimescaleDB PG18
  (`compose.postgres.yml`); Homebrew `postgresql@18` is no longer sufficient once
  either research or market data selects the `postgres` backend. `order_book_snapshots`/
  `trades` hypertables exist but stay empty this slice; paper/control keep polling
  live OHLC directly and do not write candles yet.

### 2. Portfolio and execution

- Sources: `runtime/paper*/control/*.json` and
  `runtime/paper*/execution/idempotency.sqlite`.
- Targets: portfolios, balances, positions, orders, order events, executions.
- Gate: reconcile audit fills, local positions, broker snapshots, and idempotency
  reservations. Any mismatch is quarantined rather than guessed.
- Live trading remains blocked until restart reconciliation closes the
  `reserve` to `store_result` crash window.
- **Status: implemented, not yet switched.** `EXECUTION_STORE_BACKEND=json|postgres`
  (default `json`, `EXECUTION_DATABASE_URL` for role `execution_writer`) —
  `PostgresIdempotencyStore` / `PostgresPortfolioStore`
  (`src/execution/postgres_store.py`) are drop-ins for `IdempotencyStore` and the
  JSON control-file writers used by `PaperTradingLoop`
  (`src/engine/strategy_paper.py`), wired through `scripts/paper_trading/
  run_paper_session.py`, `scripts/start_stack.py`, and the control-plane read path
  (`src/control/runtime_state.py`, additive/defensive — only overrides JSON/audit
  reads when explicitly enabled). Importer: `scripts/db/import_execution.py
  --runtime-root <frozen copy> --strategy-id <id>` — one frozen `runtime/paper*`
  directory per invocation, run once per portfolio (`paper`, `paper-kraken`,
  `paper-csv`, `paper-faza5`). `--strategy-id` is required: audit payloads carry no
  strategy identity (fixed per process via an unlogged CLI flag), so the importer
  never guesses it. Quarantines (JSONL, truncated per run — reruns reproduce, never
  accumulate): `unmapped_symbol`, `order_submitted_without_risk_decision`,
  `local_vs_broker_mismatch`, and `idempotency_no_audit_match` — the exact
  `reserve` → `store_result` crash-window gap called out above, closed going
  forward by Phase 3+4's single-transaction writes but historically unprovable, so
  it is quarantined rather than reconstructed. Validated against all four real
  `runtime/paper*` directories (frozen copies): zero quarantine entries, idempotent
  reruns (repeat imports produce zero new rows and identical destination counts).
  Degraded directories predating tracker-state persistence (`paper-kraken`,
  `paper-csv` — no `paper_tracker.json`/`simulated_broker.json`) import the known
  position quantity only; cash and `exchange_reported` balances stay unwritten
  rather than fabricated (`PostgresPortfolioStore.persist_snapshot(cash=None, ...)`).
  Cutover itself (stopping writers, flipping the backend flag, resuming) has not
  happened — remains gated on the `reserve`/`store_result` restart-reconciliation
  work called out above, per gate 6/7.

### 3. Strategies, risk, and signals

- Sources: `config/strategies.yaml`, `config/risk_limits.yaml`, and correlated audit
  events.
- Targets: strategies, strategy versions, versioned risk limits/events, signals.
- Gate: every imported decision resolves to the exact strategy/risk version active at
  its timestamp; unresolved history is reported.
- **Status: implemented, not yet switched.** Migrated by the same `migrations/
  versions/0003_execution_risk.py` as domain 2 (interdependent — `orders`/
  `signals`/`risk_events` FK into `strategy_versions`/`risk_limits`). Seeded by
  `scripts/db/seed.py::seed_execution_reference_data`: `strategy_versions` rows come
  only from immutable `config/strategy_versions/<id>/vN.json` snapshots, never
  fabricated from the mutable `strategies.yaml` alone; `risk_limits` versioning
  closes the currently-open row (`effective_to = now()`) and inserts a new one only
  when the YAML values actually differ, never updates an active version's values in
  place. `scripts/db/import_execution.py` imports `signals` (from audit `proposal`
  events) and `risk_events` (from `risk_decision`/`halt` events) alongside orders —
  see domain 2. Documented, unresolved gap: there is no historical
  version-at-timestamp tracking yet, so every imported row links to the *current*
  seeded `strategy_version_id`/`risk_limits_version_id`, not whatever version was
  active at the original decision's timestamp; the importer report sets
  `unresolved_history: true` accordingly. `risk_events.portfolio_state_snapshot`
  (`NOT NULL`) has no historical source either — the audit trail logs only
  `RiskDecision`/halt-reason, never the `PortfolioState` object `RiskEngine.
  evaluate()` saw — so imported rows carry an explicit
  `{"reconstructed": false, ...}` marker instead of a fabricated snapshot.

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
