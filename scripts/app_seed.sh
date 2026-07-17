#!/bin/bash
set -e
# .env vars come from the Makefile (`include .env` + `export`), not a bash
# `source` here — bash's own parser chokes on unquoted values containing
# spaces (e.g. BESZEL_AGENT_KEY's ssh-ed25519 value), unlike Make's.

if [ "$ENV" = "prod" ]; then
    echo "⚠️  [ABORT] Próba uruchomienia seedów na PRODUKCJI!"
    exit 1
fi

echo "🌱 Seedowanie danych..."
docker exec -i docker-postgres-1 psql \
  --username "${APPDATA_OWNER_USER}" \
  --dbname "${APP_DB}" < ./seed.sql