#!/bin/bash
set -e
source .env

if [ "$ENV" = "prod" ]; then
    echo "⚠️  [ABORT] Próba uruchomienia seedów na PRODUKCJI!"
    exit 1
fi

echo "🌱 Seedowanie danych..."
docker exec -i docker-postgres-1 psql \
  --username "${APPDATA_OWNER_USER}" \
  --dbname "${APP_DB}" < ./seed.sql