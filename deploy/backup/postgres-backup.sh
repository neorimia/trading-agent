#!/usr/bin/env bash
set -euo pipefail

: "${PG_BACKUP_DATABASE_URL:?PG_BACKUP_DATABASE_URL must be set}"

backup_dir="${PG_BACKUP_DIR:-/var/backups/trading-agent}"
target="${backup_dir}/research.dump"
temporary="${target}.tmp"

umask 077
mkdir -p "${backup_dir}"
trap 'rm -f "${temporary}"' EXIT

pg_dump \
  --dbname="${PG_BACKUP_DATABASE_URL}" \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file="${temporary}"

pg_restore --list "${temporary}" >/dev/null
mv "${temporary}" "${target}"
trap - EXIT
printf '%s\n' "${target}"
