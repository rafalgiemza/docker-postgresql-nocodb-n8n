#!/usr/bin/env bash
# =============================================================================
# backup.sh — dumps every DB this stack owns (same per-DB granularity the
# Makefile has always used, so `make restore` keeps working unchanged) into
# ./backups/*_<timestamp>.*, then pushes that directory offsite via restic
# (deduplicated, incremental) + rclone (R2/B2/etc). Local ./backups/ is left
# in place afterwards — it's still the fast path for `make restore` on the
# same host; restic is the durability layer for total-host-loss recovery
# (`restic restore` into ./backups/ first, then `make restore` as usual).
#
# Requires (see backup/mikrus-backup.env.example, kept OUTSIDE this repo on
# the VPS, e.g. /etc/mikrus-backup.env):
#   1. rclone configured with a remote named "offsite" pointing at R2 or B2
#   2. restic installed
#   3. RESTIC_PASSWORD and RESTIC_REPOSITORY exported before this script runs
#   4. `restic init` run once to create the repository
#
# Also requires the usual stack .env to be exported (Makefile does this via
# `include .env` + `export` — POSTGRES_USER/POSTGRES_DB/NC_DB/APP_DB/RAG_DB).
#
# Usage: ./backup/backup.sh [--prune]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$REPO_ROOT/backups"
TS="$(date +%F_%H%M%S)"

POSTGRES_CONTAINER="docker-postgres-1"
MONGO_CONTAINER="docker-mongodb-1"
NOCODB_VOLUME="docker_nocodb_storage"

fail() { echo "❌ FAILURE: $*" >&2; exit 1; }

: "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY not set — source /etc/mikrus-backup.env first (see backup/mikrus-backup.env.example)}"
: "${RESTIC_PASSWORD:?RESTIC_PASSWORD not set — source /etc/mikrus-backup.env first (see backup/mikrus-backup.env.example)}"

mkdir -p "$BACKUP_DIR"

echo "=== Dumping databases ($TS) ==="
docker exec "$POSTGRES_CONTAINER" pg_dumpall -U postgres --roles-only > "$BACKUP_DIR/roles_$TS.sql" \
    || fail "pg_dumpall --roles-only failed"
docker exec "$POSTGRES_CONTAINER" pg_dump -U postgres -d "$POSTGRES_DB" > "$BACKUP_DIR/n8n_$TS.sql" \
    || fail "pg_dump $POSTGRES_DB failed"
docker exec "$POSTGRES_CONTAINER" pg_dump -U postgres -d "$NC_DB" > "$BACKUP_DIR/nocodb_meta_$TS.sql" \
    || fail "pg_dump $NC_DB failed"
docker exec "$POSTGRES_CONTAINER" pg_dump -U postgres -d "$APP_DB" > "$BACKUP_DIR/appdata_$TS.sql" \
    || fail "pg_dump $APP_DB failed"
docker run --rm -v "$NOCODB_VOLUME":/data:ro -v "$BACKUP_DIR":/backup alpine \
    tar -czf "/backup/nocodb_attachments_$TS.tar.gz" -C /data . \
    || fail "NocoDB attachments tar failed"
docker exec "$MONGO_CONTAINER" mongodump --archive --db=LibreChat --quiet > "$BACKUP_DIR/mongo_$TS.archive" \
    || fail "mongodump failed"

for f in "$BACKUP_DIR/roles_$TS.sql" "$BACKUP_DIR/n8n_$TS.sql" "$BACKUP_DIR/nocodb_meta_$TS.sql" "$BACKUP_DIR/appdata_$TS.sql"; do
    [ -s "$f" ] || fail "$f is empty, aborting before it poisons the offsite backup"
done

echo "=== Pushing $BACKUP_DIR offsite via restic ==="
restic backup "$BACKUP_DIR" --tag "coaction-auto" || fail "restic backup failed"

# Keep: last 48 snapshots (~24h at 30-min cadence), 14 daily, 8 weekly.
# Prune (actually reclaim space) only once a day — pass --prune for that,
# same pattern as a separate daily cron entry.
echo "=== Applying retention policy (forget, no prune) ==="
restic forget --keep-last 48 --keep-daily 14 --keep-weekly 8 || fail "restic forget failed"

if [ "${1:-}" == "--prune" ]; then
    echo "=== Pruning old snapshots ==="
    restic prune || fail "restic prune failed"
fi

echo "=== Backup run completed successfully ($TS) ==="

# =============================================================================
# ONE-TIME SETUP NOTES (VPS)
# =============================================================================
# 1. Install tools:
#      apt install -y restic
#      curl https://rclone.org/install.sh | bash
#
# 2. Configure rclone remote (interactive):
#      rclone config
#      -> name it "offsite"
#      -> choose Cloudflare R2 or Backblaze B2, follow prompts for keys
#
# 3. Store secrets OUTSIDE this repo, e.g. /etc/mikrus-backup.env
#    (chmod 600, root-only) — see backup/mikrus-backup.env.example.
#
# 4. Initialize the repository once:
#      . /etc/mikrus-backup.env && restic init
#
# 5. Crontab (run as a user with docker access):
#      */30 * * * *  . /etc/mikrus-backup.env && cd /path/to/coaction && make backup        >> /var/log/coaction-backup.log 2>&1
#      15  3  * * *  . /etc/mikrus-backup.env && cd /path/to/coaction && make backup-prune  >> /var/log/coaction-backup.log 2>&1
#
# 6. Test restore BEFORE you need it:
#      . /etc/mikrus-backup.env && restic snapshots
#      . /etc/mikrus-backup.env && restic restore latest --target /tmp/restore-test
# =============================================================================
