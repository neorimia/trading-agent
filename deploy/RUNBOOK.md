# 24/7 Paper Trading — Deployment Runbook

Turns `docs/SERVER_DEPLOYMENT_AUDIT.md`'s Deployment Plan into copy-pasteable steps,
using the artifacts in this `deploy/` directory. Read the audit doc first if you
haven't — this runbook assumes its conclusions.

**Scope: paper trading only.** `LIVE_TRADING_ENABLED` stays `false` throughout. Live
is a separate, later engineering milestone (audit §"Live trading"), not a step here.

## 0. Before you start

- Pick a VPS: 8 dedicated vCPU / 32 GB RAM / 160–240 GB NVMe / Ubuntu 24.04, no GPU
  (audit's recommended tier; 4 vCPU / 16 GB is a tight trial-only minimum).
- You will need: SSH access, a Tailscale account, and this repo's git remote.

## 1. Provision & harden

```bash
# as root on the fresh VPS
adduser trading
usermod -aG sudo trading   # or skip if you'll sudo from your own account
ufw default deny incoming
ufw allow OpenSSH
ufw enable
# disable password auth, SSH keys only — edit /etc/ssh/sshd_config:
#   PasswordAuthentication no
systemctl restart ssh
```

## 2. Tailscale (remote access without publishing app ports)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

No app port (`8080`, `8765`, `8766`, `8767`, `11434`) is ever exposed publicly. The
only way in is SSH (restricted to your IP/tailnet) and the tailnet itself.

## 3. Runtimes

```bash
# Python 3.12 + uv
curl -LsSf https://astral.sh/uv/install.sh | sh
sudo apt install -y git
# Node 22, only if you build the console on this box (otherwise build in CI and rsync dist/)
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
```

## 4. PostgreSQL 18 (OS-managed, loopback only)

Install the PGDG PostgreSQL 18 package on the host. PostgreSQL is managed by the OS;
do not run the production database in the application process or expose port `5432`.

```bash
sudo apt install -y postgresql-common ca-certificates
sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y
sudo apt install -y postgresql-18
sudo systemctl enable --now postgresql.service
```

**TimescaleDB extension (required once the market data domain is cut over —
`docs/database-cutover-playbook.md` §"Market data"; `ohlcv_candles` is a
hypertable).** Add the Timescale apt repo and the matching PG18 package, then
preload the extension before the migration that runs `CREATE EXTENSION
timescaledb`:

```bash
curl -fsSL https://packagecloud.io/install/repositories/timescale/timescaledb/script.deb.sh | sudo bash
sudo apt install -y timescaledb-2-postgresql-18
sudo timescaledb-tune --quiet --yes   # sets shared_preload_libraries + tuning
sudo systemctl restart postgresql.service
```

Local/CI use the `timescale/timescaledb:2.29.2-pg18` Docker image instead
(`compose.postgres.yml`, `.github/workflows/ci.yml`) — same extension, packaged
differently; do not skip this step here just because it "already works" in CI.

In `/etc/postgresql/18/main/postgresql.conf`, require:

```ini
listen_addresses = '127.0.0.1,::1'
password_encryption = 'scram-sha-256'
```

In `/etc/postgresql/18/main/pg_hba.conf`, allow only the application roles over
loopback using SCRAM. Put these entries before broader `host` entries:

```text
host  trading_research  research_writer     127.0.0.1/32  scram-sha-256
host  trading_research  control_reader      127.0.0.1/32  scram-sha-256
host  trading_research  market_data_writer  127.0.0.1/32  scram-sha-256
host  trading_research  execution_writer    127.0.0.1/32  scram-sha-256
host  trading_research  backtest_writer     127.0.0.1/32  scram-sha-256
host  trading_research  audit_writer        127.0.0.1/32  scram-sha-256
host  trading_research  research_writer     ::1/128       scram-sha-256
host  trading_research  control_reader      ::1/128       scram-sha-256
host  trading_research  market_data_writer  ::1/128       scram-sha-256
host  trading_research  execution_writer    ::1/128       scram-sha-256
host  trading_research  backtest_writer     ::1/128       scram-sha-256
host  trading_research  audit_writer        ::1/128       scram-sha-256
```

(`market_data_writer`, `execution_writer`, `backtest_writer`, and `audit_writer` are
only exercised once their respective domain is cut over — skip those rows until then
if you prefer, but adding them now is harmless. `deploy/postgres/create_roles.sql`
always creates all six roles regardless of which domains are currently switched.)

Create a schema owner used only for migrations, then provision separate application
roles. Keep all six passwords distinct and out of shell history:

```bash
sudo -u postgres createuser --pwprompt --no-superuser --createdb --no-createrole trading_migrator
sudo -u postgres createdb --owner=trading_migrator trading_research
sudo -u postgres psql --dbname=trading_research <<'SQL'
REVOKE ALL ON DATABASE trading_research FROM PUBLIC;
SQL

# In a root-only shell, migrate and seed with the owner credential. Do not retain it.
read -rsp 'migration owner password: ' MIGRATOR_DB_PASSWORD; echo
export PGPASSWORD="$MIGRATOR_DB_PASSWORD"
export MIGRATION_DATABASE_URL="postgresql://trading_migrator@127.0.0.1:5432/trading_research"
cd /opt/trading-agent
sudo -u trading --preserve-env=MIGRATION_DATABASE_URL,PGPASSWORD uv run alembic upgrade head
sudo -u trading --preserve-env=MIGRATION_DATABASE_URL,PGPASSWORD uv run python scripts/db/seed.py
unset MIGRATION_DATABASE_URL PGPASSWORD MIGRATOR_DB_PASSWORD

# Read application passwords without echo, then execute the reviewed least-privilege
# grants after migrations have created the tables. All six roles are created every
# time regardless of which domains are switched yet (create_roles.sql is idempotent —
# CREATE ROLE IF NOT EXISTS-style guard — so rerunning it as later domains cut over
# is safe and expected).
read -rsp 'research writer password: ' RESEARCH_DB_PASSWORD; echo
read -rsp 'control reader password: ' CONTROL_DB_PASSWORD; echo
read -rsp 'market data writer password: ' MARKET_DATA_DB_PASSWORD; echo
read -rsp 'execution writer password: ' EXECUTION_DB_PASSWORD; echo
read -rsp 'backtest writer password: ' BACKTEST_DB_PASSWORD; echo
read -rsp 'audit writer password: ' AUDIT_DB_PASSWORD; echo
sudo -u postgres psql --dbname=trading_research \
  -v database_name=trading_research \
  -v research_password="$RESEARCH_DB_PASSWORD" \
  -v control_password="$CONTROL_DB_PASSWORD" \
  -v market_data_password="$MARKET_DATA_DB_PASSWORD" \
  -v execution_password="$EXECUTION_DB_PASSWORD" \
  -v backtest_password="$BACKTEST_DB_PASSWORD" \
  -v audit_password="$AUDIT_DB_PASSWORD" \
  -f /opt/trading-agent/deploy/postgres/create_roles.sql
unset RESEARCH_DB_PASSWORD CONTROL_DB_PASSWORD MARKET_DATA_DB_PASSWORD \
      EXECUTION_DB_PASSWORD BACKTEST_DB_PASSWORD AUDIT_DB_PASSWORD
sudo systemctl restart postgresql.service
```

Run Alembic and the idempotent seed command with `MIGRATION_DATABASE_URL` using
`trading_migrator` before applying `create_roles.sql`. Never put that owner URL in a
service `.env` file. `control_reader` receives no write or schema privileges.

Verify the effective bind before continuing:

```bash
sudo -u postgres psql --command="SHOW server_version;"
sudo -u postgres psql --command="SHOW listen_addresses;"
ss -ltn '( sport = :5432 )'
```

The version must be 18.x and every `5432` listener must be loopback. Do not add a UFW
rule for `5432`.

## 5. Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo cp deploy/systemd/ollama.service.d/override.conf /etc/systemd/system/ollama.service.d/
sudo systemctl daemon-reload
sudo systemctl enable --now ollama
ollama pull qwen3:8b
curl http://127.0.0.1:11434/api/tags   # confirm
```

## 6. Clone & install

```bash
sudo mkdir -p /opt/trading-agent
sudo chown trading:trading /opt/trading-agent
sudo -u trading git clone <this-repo-url> /opt/trading-agent
cd /opt/trading-agent
sudo -u trading uv sync --no-dev
```

## 7. Secrets

```bash
cd /opt/trading-agent
for f in control engine llm research; do
  cp .env.$f.example .env.$f
  chmod 600 .env.$f
done
```

Edit each `.env.*` (as the `trading` user):

- `.env.control`: set `CONTROL_OPERATOR_TOKEN` to a real random value
  (`openssl rand -hex 32`) — **mandatory** before any remote UI (audit risk register:
  "Empty operator token + tunnel/proxy → anyone on the path can halt/approve"). Add
  the tailnet hostname you'll browse from to `CONTROL_CORS_ORIGINS`. Before the
  backtest cutover, leave `BACKTEST_STORE_BACKEND=files` — `BacktestJobManager`
  keeps writing `backtests/jobs/*.json`/`backtests/reports/*.json` unconditionally
  either way. At that cutover, set it to `postgres` and set
  `BACKTEST_DATABASE_URL=postgresql://backtest_writer:<percent-encoded-password>@127.0.0.1:5432/trading_research`
  — role `backtest_writer`, never `execution_writer`/`control_reader`'s
  credentials. Import history first with `scripts/db/import_backtests.py
  --backtests-root <frozen copy of backtests/>` (`--runtime-root <frozen copy of
  runtime/> --paper-strategy-id <id>` too, if paper history should be imported in
  the   same pass). See `docs/database-cutover-playbook.md` §"Backtest and paper
  runs" for the full quarantine/reconciliation contract. Rollback: set
  `BACKTEST_STORE_BACKEND=files` again and restart `trading-control` — the JSON
  files were never stopped, so nothing to replay.
- `.env.control` + `.env.engine` (**must be set identically in both** — control
  and engine write the same `audit_log` through one shared role): before the
  audit cutover, leave `AUDIT_STORE_BACKEND=files` in both files —
  `AuditLog`/`ApprovalGate` keep writing `audit.sqlite` and
  `control/approvals/*.json` unconditionally either way. At that cutover, set it
  to `postgres` in both `.env.control` and `.env.engine` and set the same
  `AUDIT_DATABASE_URL=postgresql://audit_writer:<percent-encoded-password>@127.0.0.1:5432/trading_research`
  in both — role `audit_writer`, never `backtest_writer`/`execution_writer`/
  `control_reader`'s credentials. Import history first with
  `scripts/db/import_audit.py --runtime-root <frozen copy of runtime/> [--runtime-root ...]`
  (repeatable, one per frozen `runtime/paper*` directory). See
  `docs/database-cutover-playbook.md` §"Audit, approvals, and system events" for
  the full quarantine/reconciliation contract, including the `human_approvals`
  single-writer note and the `system_events`/`agent_runs`/`alerts`
  no-legacy-source caveat. Rollback: set `AUDIT_STORE_BACKEND=files` again in
  both `.env.control` and `.env.engine`, then restart `trading-control` and the
  paper engine — the SQLite/JSON files were never stopped, so nothing to
  replay.
- `.env.engine`: leave `LIVE_TRADING_ENABLED=false`. Leave `KRAKEN_*` trading keys
  empty. `BROKER_PAPER_MODE=true`. **Never copy laptop live keys here.** Before the
  market data cutover, leave `MARKET_DATA_STORE_BACKEND=files` (backtest CLI only —
  paper/control still poll live OHLC directly, they do not write candles this
  slice). At that cutover, set it to `postgres` and set
  `MARKET_DATA_DATABASE_URL=postgresql://market_data_writer:<percent-encoded-password>@127.0.0.1:5432/trading_research`
  — role `market_data_writer`, never `research_writer`/`control_reader`'s
  credentials. See `docs/database-cutover-playbook.md` §"Market data" for the
  backfill/reconciliation steps (`scripts/db/import_market_data.py`). `paper_trading_runs`
  has no separate flag — it piggy-backs on `EXECUTION_STORE_BACKEND` (domain 2's
  cutover), so `scripts/paper_trading/run_paper_session.py` starts upserting it the
  moment that switch flips, with no extra `.env.engine` change here.
- `.env.llm`: confirm `OLLAMA_HOST=http://127.0.0.1:11434`.
- `.env.research`: fill research API keys. Before cutover, keep
  `RESEARCH_STORE_BACKEND=sqlite`. At the switch, set it to `postgres` and set
  `RESEARCH_DATABASE_URL=postgresql://research_writer:<percent-encoded-password>@127.0.0.1:5432/trading_research`.
- `.env.control`: switch its own `RESEARCH_STORE_BACKEND=postgres` at the same cutover
  and set
  `CONTROL_DATABASE_URL=postgresql://control_reader:<percent-encoded-password>@127.0.0.1:5432/trading_research`
  for the control plane's read-only connection.

The two database passwords must be different. The writer URL exists only in
`.env.research`; the reader URL exists only in `.env.control`. Never put either in
`.env.engine`, service unit files, shell history, logs, or committed files. Keep all
real `.env.*` files owned by `trading` and mode `0600`.

## 8. systemd units

```bash
cd /opt/trading-agent
sudo cp deploy/systemd/trading-llm.service /etc/systemd/system/
sudo cp deploy/systemd/trading-research.service /etc/systemd/system/   # only if using research
sudo cp deploy/systemd/trading-control.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now trading-llm
sudo systemctl enable --now trading-research   # if applicable
sudo systemctl enable --now trading-control
```

`trading-research.service` has `After=` and `Wants=` dependencies on
`postgresql.service`. `Wants=` intentionally permits the research process to start
and report not-ready rather than making PostgreSQL failure look like process
liveness failure.

Do **not** enable/run `scripts/dev/start_stack.py` here — it is not the production
supervisor (it stops the whole stack on any single child exit).

## 9. Console (nginx)

```bash
cd /opt/trading-agent/apps/console
npm ci
npm run build   # → dist/console/browser/
sudo cp /opt/trading-agent/deploy/nginx/trading-console.conf /etc/nginx/sites-available/trading-console
sudo ln -s /etc/nginx/sites-available/trading-console /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Read the comments in `deploy/nginx/trading-console.conf` — bind it to the tailnet
interface, not `0.0.0.0`.

## 10. Cron, logrotate, backups

```bash
sudo -u trading crontab -e   # paste the line from deploy/cron/research-ingest.cron
sudo cp deploy/logrotate/trading-agent /etc/logrotate.d/trading-agent
sudo logrotate --debug /etc/logrotate.d/trading-agent   # dry run
```

Follow `deploy/backup/README.md` for restic setup, then run the restore drill once —
an untested backup is not a backup.

## 11. Health and readiness

The research endpoints have distinct contracts:

```bash
# Process liveness only; it must not query PostgreSQL.
curl --fail http://127.0.0.1:8766/health

# Database readiness; this must fail while PostgreSQL is unavailable or unusable.
curl --fail http://127.0.0.1:8766/ready
```

Use `/health` for process supervision and `/ready` for deployment/cutover gates. Do
not redefine `/health` as a database check.

```bash
curl http://127.0.0.1:8767/v1/health -H "Authorization: Bearer $CONTROL_OPERATOR_TOKEN"
```

Confirm `llm: "up"`, `ollama: "up"`, `agent: "stopped"` (paper hasn't started yet).

Set up an external check (cron `curl` + alert, or Uptime Kuma/Netdata/Beszel over
Tailscale) against `/v1/health` and Ollama's `/api/tags`.

## 12. Research cutover: SQLite to PostgreSQL

Keep the SQLite file and a fresh backup until the PostgreSQL cutover has passed its
acceptance window. Perform the following in order; do not overlap old and new
writers.

### Preflight

1. Confirm PostgreSQL 18 is loopback-only, migrations are current, both application
   roles connect, and `control_reader` cannot write.
2. Run `deploy/backup/README.md`'s `pg_dump` then restic sequence and confirm it
   completed. Also make a separately named copy of the SQLite metadata DB.
3. Record current SQLite row counts and the source file hash. Prepare the approved,
   version-matched importer and reconciliation command; do not improvise a new
   transformation during the maintenance window.

### Stop, import, reconcile, switch, restart

1. **Stop cron:** disable the `research-ingest` cron entry and verify no ingest is
   running. This freezes SQLite before its final copy.
2. **Stop services:** `sudo systemctl stop trading-control trading-research`.
3. **Import:** with `MIGRATION_DATABASE_URL` set to the migration-owner DSN, run:
   `uv run python scripts/db/import_research.py --sqlite data/research/metadata.db
   --report runtime/migrations/research-import.json`. Run the same command a second
   time and require identical destination counts; a non-zero exit aborts the cutover.
4. **Reconcile:** inspect the generated JSON report. Require no unresolved sources,
   no missing sample hashes, explained unmapped instruments, expected canonical and
   occurrence counts, and identical second-run counts. Save the report with the
   maintenance record. Any unexplained mismatch aborts the cutover.
5. **Switch configuration:** in `.env.research`, set
   `RESEARCH_STORE_BACKEND=postgres` and its writer-only
   `RESEARCH_DATABASE_URL`. In `.env.control`, set the reader-only
   `CONTROL_DATABASE_URL` and `RESEARCH_STORE_BACKEND=postgres`. Keep the SQLite
   path unchanged for rollback.
6. **Restart:** run
   `sudo systemctl restart postgresql.service trading-research trading-control`.
   Require both research `/health` and `/ready` to succeed, then verify the control
   plane can read research data.
7. **Resume cron:** re-enable research ingest only after readiness and read-path
   verification. Observe at least one ingest, confirm PostgreSQL row growth and
   deduplication, then take a fresh `pg_dump` followed by restic.

### Rollback

Rollback before resuming cron is lossless because SQLite remained frozen:

1. Keep cron disabled and stop `trading-control` and `trading-research`.
2. Set `RESEARCH_STORE_BACKEND=sqlite` in both `.env.research` and `.env.control`;
   retain/clear the PostgreSQL URLs as appropriate, but do not copy writer
   credentials into control.
3. Restore the frozen SQLite file if it was altered, then restart research and
   control.
4. Require `/health`, the SQLite-backed `/ready`, and a control-plane research read
   to succeed before re-enabling cron.

If any PostgreSQL writes occurred after cron was resumed, first export/replay those
writes into SQLite or accept the documented data-loss boundary. Never silently point
the service at the old SQLite snapshot. Preserve the failed PostgreSQL database and
reconciliation report for diagnosis; do not drop or mutate them during rollback.

## 12.1 Paper execution + audit rehearsal (local, non-production)

Same gates as §12, run against a **local** PostgreSQL and a **frozen copy** of one
`runtime/paper*` directory — no `.env.*` file on any production host is touched by
this section. Scope is deliberately narrow: one tree (`runtime/paper`), two domains
(execution, then audit, per `docs/database-cutover-playbook.md` domain order),
`EXECUTION_STORE_BACKEND` left at `json`. This is a rehearsal to prove the importers,
role grants, and the audit dual-write path before any production backend flip — it
is not itself a production cutover.

**Rehearsal run:** 2026-09-22, `runtime/paper`, frozen to
`/tmp/paper-frozen-20260922` (local temp dir, never committed).
`audit.sqlite` sha256: `e63ce5eec69d1f4cdb2f0e4ab430dbbaee6c11efb63df92d009fed6c10db4ef6`.
`--strategy-id baseline_ema_cross`, `--portfolio-name paper`.

### Preflight

1. Stop the local control process (`kill -TERM <pid>` on port `8767`); confirm no
   `run_paper_session.py` process is running.
2. Checkpoint the audit SQLite WAL into the main file so the freeze captures
   everything: `sqlite3 runtime/paper/audit/audit.sqlite "PRAGMA
   wal_checkpoint(TRUNCATE);"`.
3. Freeze: `cp -a runtime/paper /tmp/paper-frozen-YYYYMMDD` — never import the live
   tree. Record source counts and the `audit.sqlite` hash from the **frozen copy**.

Source snapshot (frozen copy): 141 `audit_events` (51 `operator_action`, 31
`risk_decision`, 31 `proposal`, 15 `reconciliation_ok`, 6 `analysis`, 2
`order_submitted`, 2 `human_approval`, 2 `fill`, 1 `discovery_summary`); 3 approval
request/decision file pairs (2 approved, 1 denied — the denied one correctly has no
`order_submitted`/`fill`); 2 `idempotency.sqlite` reservations.

Pre-import destination baseline (`trading_research`, `paper` portfolio): `orders=1`
— a pre-existing row unrelated to this freeze (different `client_order_id`, imported
before this rehearsal). Recorded, not deleted, so the post-import count is
explainable as leftover + imported.

### Import execution, then audit (each: dry-run, commit, identical rerun)

```bash
export MIGRATION_DATABASE_URL="postgresql://trading_migrator:<password>@127.0.0.1:5432/trading_research"
uv run python scripts/db/seed.py

uv run python scripts/db/import_execution.py \
  --runtime-root /tmp/paper-frozen-YYYYMMDD --portfolio-name paper \
  --strategy-id baseline_ema_cross \
  --report runtime/migrations/execution-import-paper.json

uv run python scripts/db/import_audit.py \
  --runtime-root /tmp/paper-frozen-YYYYMMDD \
  --report runtime/migrations/audit-import-paper.json
```

Run each command a second time and require identical `destination` counts; a
non-zero exit or a changed count aborts the rehearsal. Reports and quarantine files
live under gitignored `runtime/migrations/`.

**Results (this run):**

| Table | Pre-import | 1st commit | 2nd commit (rerun) | Match? |
|---|---|---|---|---|
| `orders` (execution) | 1 (leftover) | 3 | 3 | yes |
| `order_events` | 0 | 4 | 4 | yes |
| `executions` | 0 | 2 | 2 | yes |
| `positions` | 0 | 1 | 1 | yes |
| `balances` | 0 | 3 | 3 | yes |
| `risk_events_for_portfolio_orders` | 0 | 2 | 2 | yes |
| `risk_events_standalone_system_wide` | 0 | 29 | 29 | yes |
| `audit_log` | 0 | 141 | 141 | yes |
| `human_approvals` | 0 | 3 | 3 | yes |

Execution quarantine: 0. `unresolved_history: true` (expected — no
version-at-timestamp tracking yet; every imported row links to the current
strategy/risk version, per the cutover playbook gate). Audit quarantine: 0.
`order_id_resolved: 2`, `order_id_unresolved: 0` (execution imported first, so both
`order_submitted` correlations resolve). `expires_at_reconstructed: 3` (approval
timeout was never persisted per-request on disk — honesty flag, not a failure). On
rerun, `history_imported`/`audit_log_imported` are all `0` (except
`human_approvals_imported: 3`, which is expected — decision fields are re-applied on
every rerun by design, always with the same values).

### Role isolation (`deploy/postgres/create_roles.sql`)

Checked with tagged throwaway rows, cleaned up as `trading_migrator` immediately
after (verified counts returned to the post-import baseline):

| Check | Result |
|---|---|
| `audit_writer` INSERT `audit_log` | succeeded |
| `audit_writer` UPDATE `audit_log` | blocked, `42501 insufficient_privilege` |
| `audit_writer` DELETE `audit_log` | blocked, `42501 insufficient_privilege` |
| `audit_writer` INSERT + UPDATE `human_approvals` | succeeded |
| `control_reader` SELECT `audit_log`/`orders` | succeeded |
| `control_reader` INSERT `audit_log` | blocked, `42501 insufficient_privilege` |
| `execution_writer` INSERT `order_events` | succeeded |
| `execution_writer` UPDATE/DELETE `order_events` | blocked, `42501 insufficient_privilege` |
| `execution_writer` UPDATE `orders.status` | succeeded (orders is mutable by design) |

### Enable `AUDIT_STORE_BACKEND=postgres` locally, smoke test, do not flip production

In local (gitignored) `.env.control` **and** `.env.engine`, identically:

```text
AUDIT_STORE_BACKEND=postgres
AUDIT_DATABASE_URL=postgresql://audit_writer:<password>@127.0.0.1:5432/trading_research
```

`EXECUTION_STORE_BACKEND` stays `json` in both files — deliberately not flipped in
this rehearsal.

Restarted the local control process; `GET /v1/health` returned `200`. Triggered
`POST /v1/risk/halt/reset` (a real operator action, idempotency-keyed) to exercise
the audit write path: `audit_log` went `141 → 142` and `runtime/paper/audit/audit.sqlite`
went `141 → 142` in the same call — confirming `DualWriteAuditLog` writes both stores
unconditionally, matching `src/audit/postgres_store.py::open_audit_log`. The new
`audit_log` row is a genuine `operator_action`/`halt_reset` event, kept (not deleted)
per the append-only, never-fabricate-or-delete-real-history policy already applied
to `audit_log`'s grants. Side effect: `runtime/paper/control/halt.flag` was genuinely
cleared by this action; no paper engine process was running at the time, so this had
no operational effect, but note it if you reuse this exact runtime tree.

**Do not flip production `.env.control`/`.env.engine`** and **do not flip
`EXECUTION_STORE_BACKEND`** as a result of this rehearsal — those remain separate,
later steps gated on the restart-reconciliation work called out in
`docs/database-cutover-playbook.md` domain 2. Rollback (not exercised beyond what's
already true): set `AUDIT_STORE_BACKEND=files` again in both files and restart — the
SQLite/JSON files were never stopped, so nothing to replay.

### Not in scope for this rehearsal

- `paper-kraken`, `paper-csv`, `paper-faza5` — only `paper` was frozen/imported.
- `import_backtests.py` — the requested sequence was execution → audit only.
- Any production host — this section runs entirely against local PostgreSQL.

## 13. Start paper

Over the tailnet (SSH tunnel or the nginx UI from step 9):

```bash
curl -X POST http://127.0.0.1:8767/v1/agent/start \
  -H "Authorization: Bearer $CONTROL_OPERATOR_TOKEN" \
  -H "Idempotency-Key: boot-$(date +%s)"
```

Confirm the ApprovalGate is still required (a proposal should show up as pending, not
auto-execute).

## 14. Paper validation (days, not minutes)

Do not consider this done after step 13. Over the following days, confirm:

- [ ] A few 1h bars post through the loop; approve/reject from the remote UI works.
- [ ] `kill -9 <paper pid>` and confirm `trading-control` (or the operator, since
      control's `SubprocessAgentProcess.start` de-dupes against a live `agent_pid`)
      restarts it without duplicate simulated fills.
- [ ] `sudo systemctl stop ollama`, confirm proposals become `RejectedProposal`
      (fail-closed), not silently skipped or crashed.
- [ ] `sudo reboot`, confirm `ollama`, `trading-llm`, `trading-control` all come back
      via systemd without manual intervention.
- [ ] Leave a heartbeat stale on purpose (stop the paper process without restarting
      it) and confirm the control plane's own watchdog
      (`src/control/runtime_state.py:halt_if_heartbeat_stale`, checked every
      ≤30s independent of any dashboard client) halts instead of sitting silent.

## What NOT to do as part of this

- Buy a GPU (CPU is sufficient for `qwen3:8b` Q4_K_M at this request rate).
- Expose `5432`, `11434`, `8765`, `8766`, or `8767` on a public interface.
- Set `LIVE_TRADING_ENABLED=true`. See `docs/SERVER_DEPLOYMENT_AUDIT.md` §"Live
  trading (separate milestone)" for what that actually requires — it is not a config
  flag flip.
