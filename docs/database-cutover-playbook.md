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

- Sources: `backtests/jobs/*.json`, `backtests/reports/**/manifest.json`, trade
  reports, and each `runtime/paper*` directory.
- Targets: backtest runs/trades and paper-trading runs.
- Gate: run IDs, dataset hashes, seeds, strategy versions, metrics, and on-disk report
  pointers reproduce the legacy manifests.
- **Status: implemented, not yet switched.** Migrated by `migrations/versions/
  0004_backtest_paper_runs.py` (`backtest_run_id`/`backtest_run_id` FK into
  `strategy_versions`/`instruments`; `paper_trading_runs` adds `UNIQUE
  (portfolio_id)` — the four `runtime/paper*` directories are long-lived runs, not
  one row per session). `BACKTEST_STORE_BACKEND=files|postgres` (default `files`,
  `BACKTEST_DATABASE_URL` for role `backtest_writer`) gates
  `src/control/backtest_jobs.py::BacktestJobManager` and `scripts/backtest/
  run_backtest.py`'s CLI suite; `paper_trading_runs` piggy-backs on the existing
  `EXECUTION_STORE_BACKEND=json|postgres` (domain 2) instead of a third flag. JSON/
  report files stay the unconditional rollback target in every case — the Postgres
  write is strictly additive. `PortfolioTracker` (`src/engine/portfolio_tracker.py`)
  now records structured round-trip trades (`ClosedTrade`: entry/exit time, price,
  quantity, pnl, fees, exit_reason) alongside the legacy PnL-only `closed_trades`
  list, fed by `timestamp=` now required on every `on_fill` call site (`strategy_
  adapter`/`strategy_baseline`/`strategy_llm_assisted`/`strategy_paper`). Importer:
  `scripts/db/import_backtests.py --backtests-root <frozen copy> [--runtime-root
  <frozen copy> --paper-strategy-id <id>]` — job/CLI-suite rows use a deterministic
  primary key (`run_id` verbatim; `uuid5(suite_run_id, kind, multiplier)` for CLI
  children) with `ON CONFLICT DO NOTHING`; paper runs `UPSERT` on `portfolio_id`
  with an explicit `sessions_count` (never incremented on a rerun, unlike the
  going-forward writer). Quarantines (JSONL, truncated per run):
  `unmapped_symbol`, `unmapped_strategy_version`, `unmapped_portfolio`, and
  `dataset_hash_missing` — `backtest_runs.dataset_hash` is `NOT NULL` and job JSON
  only ever carries it on the `done` success path, so `queued`/`running`/`error`
  job records are always quarantined rather than inserted with a guessed hash.
  Documented, unreconstructable gaps (never fabricated): job/CLI-suite JSON never
  recorded `universe_sha256` before this phase, so the importer hashes the
  *current* `config/universe.yaml` and reports it under
  `universe_sha256_reconstructed_count`; `metrics_{kind}_{Nx}.json` (CLI suite)
  never carried per-trade records, so those runs' `backtest_trades` are always
  `trades_not_reconstructable: N` (zero rows inserted, never guessed from PnL);
  `paper_trading_runs.config_snapshot` for an imported run is built from the
  *current* `paper_trading.yaml`/`risk_limits.yaml` (the config in effect when a
  frozen directory last ran is not persisted anywhere), flagged
  `reconstructed_from_current_config: true`. Cutover itself (stopping writers,
  flipping the backend flag, resuming) has not happened.

### 5. Audit, approvals, and system events

- Sources: `audit.sqlite`, approval request/decision JSON files, heartbeat and
  reconciliation history that has business value.
- Targets: append-only audit, human approvals, agent runs, alerts, system events.
- Cut this domain over last.
- Gate: correlation chains remain complete, pagination is stable, append-only grants
  are enforced, and no approval decision is orphaned.
- **Status: implemented, not yet switched.** Migrated by `migrations/versions/
  0005_audit_agent_approvals.py`: `agent_runs`, `audit_log` (CHECK `event_type`
  against the 14 values already live in `src/audit/events.py::AuditEventType`,
  no separate placeholder list), `agent_actions` (`CREATE VIEW`, six narrative
  event types), `system_events`, `human_approvals`, `alerts`.
  `AUDIT_STORE_BACKEND=files|postgres` (default `files`, `AUDIT_DATABASE_URL`)
  gates both `.env.control` and `.env.engine` identically — control and engine
  write the same `audit_log` through one shared role, `audit_writer` (unlike
  every prior domain's single-owning-process role split), which is granted
  INSERT-only on `audit_log` (`REVOKE UPDATE, DELETE` enforced at the role level,
  not just by omission) and INSERT+UPDATE on the other four tables.
  `audit.sqlite`/the approval JSON files stay the unconditional rollback target
  in every case — `open_audit_log()` (`src/audit/postgres_store.py`) is a
  drop-in `AuditLog` subclass, so every existing call site
  (`src/control/runtime_state.py::_audit`, `src/control/agent_process.py`,
  `scripts/paper_trading/run_paper_session.py`) just swaps the constructor.
  Documented deviations (never fabricated): `human_approvals.order_id` is
  nullable (still `UNIQUE`) — a denied/timed-out approval never produces an
  `orders` row, since `order_submitted` only fires after approval succeeds;
  `decided_by`/`reason` are nullable — unknown at request (INSERT) time, only
  known at decision (UPDATE) time. `human_approvals` has a single writer,
  `ApprovalGate.request()` (engine): it is the one call that observes both the
  request and the eventual decision, whichever process wrote the `.decision.json`
  file, so `write_approval()` (control) never needs its own Postgres write —
  avoiding a second, racier writer for the same row. `order_id` links only when
  `EXECUTION_STORE_BACKEND=postgres` too (that backend is what actually inserts
  the `orders` row `order_id` references — `orders.order_id = correlation_id`),
  otherwise left NULL. `agent_runs` (INSERT at engine start, UPDATE
  `stopped_at`/`stop_reason` at graceful shutdown) is gated on both
  `AUDIT_STORE_BACKEND=postgres` and `EXECUTION_STORE_BACKEND=postgres` (the
  latter is what resolves `strategy_version_id`, `NOT NULL` in the schema — never
  guessed when unresolvable). `system_events` is instrumented at agent
  start/stop and broker-monitor start (`src/control/agent_process.py`) and the
  heartbeat-stale halt watchdog (`runtime_state.py::halt_if_heartbeat_stale`) —
  not exhaustively, only at existing clear hook points. `alerts` stays
  fully ephemeral for reads (`build_alerts()`); `record_alerts()` additionally
  persists a new row only when no unresolved row of the same title already
  exists (dedup, no poll-driven duplicate spam), with two new operator-only
  endpoints, `POST /v1/alerts/{alert_id}/ack` and `.../resolve`.
  `system_events`/`agent_runs`/`alerts` have no legacy on-disk source at all —
  new instrumentation, not a migration; the importer's report says so
  explicitly rather than silently skipping them. Importer:
  `scripts/db/import_audit.py --runtime-root <frozen copy> [--runtime-root ...]`
  for `audit_log` (dedup on `(correlation_id, event_type, "timestamp")`) and
  `human_approvals` (`approval_id = correlation_id`, `ON CONFLICT DO NOTHING` +
  a re-applied `UPDATE` for the decision fields). Documented, unreconstructable
  gap: `human_approvals.expires_at` (`NOT NULL`) was never persisted per-request
  on disk — reconstructed as `requested_at + approval_timeout_s` from the same
  `paper_trading.yaml` source `ApprovalGate.request()` itself reads, flagged
  `expires_at_reconstructed` in the report. Cutover itself (stopping writers,
  flipping the backend flag, resuming) has not happened.

## Operations after all paper domains are cut over

- Keep halt flags, PID files, and immutable research/backtest blobs on disk.
- Continue daily logical dumps plus restic and periodic restore drills.
- Add WAL archiving and point-in-time recovery only before 24/7 live trading.
- Remove a legacy adapter/path only in a separate cleanup change after its rollback
  window has expired.
