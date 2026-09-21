# Backups

Daily, encrypted, and off the VPS. PostgreSQL is backed up with a consistent logical
dump **before** restic snapshots the files. Never point restic at PostgreSQL's live
data directory.

## What to back up

- `/var/backups/trading-agent/research.dump` — completed `pg_dump` custom archive.
- `runtime/` — heartbeat, halt flag, reconciliation state, and any remaining local
  paper-trading state.
- `config/` — risk limits, universe, strategies, and paper-trading config.
- `data/research/` — raw research blobs; PostgreSQL stores metadata, not these blobs.
- `.env.control`, `.env.engine`, `.env.llm`, `.env.research` — only inside the
  encrypted restic repository. These files remain mode `0600`.

Do not back up PostgreSQL's live data directory, `.venv/`, `node_modules/`, or
`graphify-out/cache/`.

## Daily sequence

Run the whole sequence from a root-owned systemd timer or equivalent locked-down
backup job. The job must stop if `pg_dump` fails; restic must never upload a stale
dump as if it were current.

```bash
# One-time: choose a remote repository that is not on this VPS.
restic init --repo b2:your-bucket:trading-agent

# Each run: make a transactionally consistent dump, publish it atomically, then restic.
install -d -o postgres -g postgres -m 0700 /var/backups/trading-agent
sudo -u postgres env \
  PG_BACKUP_DATABASE_URL=postgresql:///trading_research \
  PG_BACKUP_DIR=/var/backups/trading-agent \
  /opt/trading-agent/deploy/backup/postgres-backup.sh

# Run this only after pg_dump succeeds.
restic backup \
  /var/backups/trading-agent/research.dump \
  /opt/trading-agent/runtime \
  /opt/trading-agent/config \
  /opt/trading-agent/data/research \
  /opt/trading-agent/.env.control \
  /opt/trading-agent/.env.engine \
  /opt/trading-agent/.env.llm \
  /opt/trading-agent/.env.research \
  --exclude-caches

restic forget --keep-daily 14 --keep-weekly 8 --keep-monthly 6 --prune
restic check
```

The dump is created through the local PostgreSQL peer-authenticated `postgres` OS
account, so the backup job does not need either application database password. Keep
the restic repository password and object-storage credentials in a root-readable
credential file or systemd credential, and keep a recovery copy in a password
manager off the VPS. Never add them to `.env.research` or `.env.control`.

## Restore drill

Run after initial setup, after schema or backup-job changes, and at least quarterly.
The drill restores into a disposable database; it never overwrites production.

```bash
rm -rf /tmp/trading-agent-restore
restic snapshots
restic restore latest --target /tmp/trading-agent-restore

sudo -u postgres dropdb --if-exists trading_research_restore
sudo -u postgres createdb trading_research_restore
sudo -u postgres pg_restore \
  --exit-on-error \
  --no-owner \
  --dbname=trading_research_restore \
  /tmp/trading-agent-restore/var/backups/trading-agent/research.dump

# Schema and representative critical-table checks must succeed.
sudo -u postgres psql --dbname=trading_research_restore \
  --command='\dt'
sudo -u postgres psql --dbname=trading_research_restore \
  --command='SELECT count(*) FROM research_documents;'
sudo -u postgres psql --dbname=trading_research_restore \
  --command='SELECT count(*) FROM research_analyses;'

sudo -u postgres dropdb trading_research_restore
rm -rf /tmp/trading-agent-restore
```

Record the snapshot ID, date, restore duration, archive errors, and row counts. Compare
the restored counts with production counts captured at backup time; investigate any
unexpected difference. A successful `restic restore` without a successful
`pg_restore` and SQL verification is not a completed drill.
