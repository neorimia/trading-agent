# Backups

Per `docs/SERVER_DEPLOYMENT_AUDIT.md` "Backup Strategy": daily, off the VPS, encrypted.

## What to back up

- `runtime/` — audit SQLite DB, heartbeat, halt flag, reconciliation state, local
  positions, approvals. This is the reconstructable record of everything the agent did.
- `config/` — risk limits, universe, strategies, paper trading config.
- `.env.control`, `.env.engine`, `.env.llm`, `.env.research` — **encrypted**. These
  never contain live trading keys in paper mode (`LIVE_TRADING_ENABLED=false`, Kraken
  trading keys empty), but `CONTROL_OPERATOR_TOKEN` and any research API keys still
  matter.
- `data/research/` — ingested research corpus (optional; can be re-ingested, but
  saves re-fetching history).

Do **not** back up `.venv/`, `node_modules/`, or anything under `graphify-out/cache/` —
regenerable, and bloats the backup.

## How

Restic to a remote/off-box repository (Backblaze B2, an object storage bucket, or a
second VPS — anywhere that isn't this machine's own disk).

```bash
# one-time init (choose your own restic backend URL)
restic init --repo b2:your-bucket:trading-agent

# daily backup — run as the `trading` user via cron or a systemd timer
restic backup \
  /opt/trading-agent/runtime \
  /opt/trading-agent/config \
  /opt/trading-agent/data/research \
  /opt/trading-agent/.env.control \
  /opt/trading-agent/.env.engine \
  /opt/trading-agent/.env.llm \
  /opt/trading-agent/.env.research \
  --exclude-caches

# retention
restic forget --keep-daily 14 --keep-weekly 8 --keep-monthly 6 --prune
```

Store the restic repository password and B2 (or equivalent) credentials somewhere
that is NOT on the VPS itself — a password manager, not a file next to the backup job.

## Restore drill

Do this once after first setting up backups, and again after any config change:

```bash
restic snapshots
restic restore latest --target /tmp/restore-check
diff -r /tmp/restore-check/runtime /opt/trading-agent/runtime
```

An untested backup is not a backup.
