#!/usr/bin/env bash
# =============================================================================
# restore.sh — restores everything backup.sh produced (./backups/*_<ts>.*)
# back into a running stack. Counterpart to backup.sh; see that file for what
# gets backed up and why.
#
# n8n/nocodb hold live connections to their own Postgres databases the moment
# they're running, and DROP DATABASE blocks on any open connection — so this
# only brings up postgres/mongodb first, restores everything, then starts the
# rest of the stack at the end. pg_terminate_backend before each DROP also
# clears stray host-side connections (e.g. a DB GUI client left open against
# the published 127.0.0.1:5432 port) that would block the drop the same way.
#
# Requires the usual stack .env to be exported (Makefile does this via
# `include .env` + `export` — POSTGRES_DB/NC_DB/APP_DB).
#
# Usage: ./backup/restore.sh <timestamp>   (matches ./backups/*_<timestamp>.*)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$REPO_ROOT/backups"
DC_CMD="docker compose -f $REPO_ROOT/docker-compose.yml"

POSTGRES_CONTAINER="docker-postgres-1"
MONGO_CONTAINER="docker-mongodb-1"
NOCODB_VOLUME="docker_nocodb_storage"
SEAWEEDFS_VOLUME="docker_seaweedfs_storage"

TS="${1:-}"

fail() { echo "❌ FAILURE: $*" >&2; exit 1; }

[ -n "$TS" ] || fail "Brak RESTORE_TS — nie znaleziono żadnych plików backupu w $BACKUP_DIR? Podaj RESTORE_TS=<ts> albo zrób najpierw 'make backup'."

echo "🚀 Rozpoczynam przywracanie z backupu: $TS"

echo "📦 1/8 Podnoszę tylko bazy danych (postgres/mongo) — n8n/nocodb muszą zostać wyłączone, inaczej złapią połączenie przed DROP DATABASE..."
$DC_CMD up -d postgres mongodb
echo "⏳ Czekam 15 sekund, aż bazy danych będą gotowe na przyjmowanie połączeń..."
sleep 15

echo "🗄️ 2/8 Tworzę bazy danych (ubijam zalegające sesje, czyszczę jeśli już istnieją)..."
for db in "$POSTGRES_DB" "$NC_DB" "$APP_DB"; do
    docker exec "$POSTGRES_CONTAINER" psql -U postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$db' AND pid <> pg_backend_pid();"
    docker exec "$POSTGRES_CONTAINER" psql -U postgres -c "DROP DATABASE IF EXISTS $db;"
done
for db in "$POSTGRES_DB" "$NC_DB" "$APP_DB"; do
    docker exec "$POSTGRES_CONTAINER" psql -U postgres -c "CREATE DATABASE $db;"
done

echo "🔑 3/8 Przywracanie globalnych ról..."
cat "$BACKUP_DIR/roles_$TS.sql" | docker exec -i "$POSTGRES_CONTAINER" psql -U postgres || true

echo "💾 4/8 Przywracanie struktury i danych z plików SQL..."
echo "   -> Wgrywam bazę n8n..."
cat "$BACKUP_DIR/n8n_$TS.sql" | docker exec -i "$POSTGRES_CONTAINER" psql -U postgres -d "$POSTGRES_DB"
echo "   -> Wgrywam bazę NocoDB Meta..."
cat "$BACKUP_DIR/nocodb_meta_$TS.sql" | docker exec -i "$POSTGRES_CONTAINER" psql -U postgres -d "$NC_DB"
echo "   -> Wgrywam bazę AppData..."
cat "$BACKUP_DIR/appdata_$TS.sql" | docker exec -i "$POSTGRES_CONTAINER" psql -U postgres -d "$APP_DB"

echo "📂 5/8 Wypakowuję wolumen NocoDB (cache/config, nie załączniki)..."
docker run --rm -v "$NOCODB_VOLUME":/data -v "$BACKUP_DIR":/backup alpine \
    tar -xzf "/backup/nocodb_data_$TS.tar.gz" -C /data

echo "📦 6/8 Wypakowuję wolumen SeaweedFS (attachments/offers/recordings/transcripts)..."
docker run --rm -v "$SEAWEEDFS_VOLUME":/data -v "$BACKUP_DIR":/backup alpine \
    tar -xzf "/backup/seaweedfs_$TS.tar.gz" -C /data

echo "🍃 7/8 Przywracanie bazy MongoDB (LibreChat)..."
if [ -f "$BACKUP_DIR/mongo_$TS.archive" ]; then
    cat "$BACKUP_DIR/mongo_$TS.archive" | docker exec -i "$MONGO_CONTAINER" mongorestore --archive --drop
    echo "   -> MongoDB przywrócone."
else
    echo "   -> Brak pliku mongo_$TS.archive. Pomijam ten krok."
fi

echo "🔄 8/8 Podnoszę resztę stacka (n8n/nocodb/seaweedfs/...), by zaczytała przywrócone dane..."
$DC_CMD up -d

echo "✅ Success!"
