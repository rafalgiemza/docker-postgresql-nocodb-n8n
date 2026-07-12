#!/bin/bash
set -e
source .env

if [ "$ENV" = "prod" ]; then
    echo "⚠️  [ABORT] Próba uruchomienia danych demo na PRODUKCJI!"
    exit 1
fi

echo "🧪 Seedowanie danych demo (Offer Builder fixture)..."
docker exec -i docker-postgres-1 psql \
  --username "${APPDATA_OWNER_USER}" \
  --dbname "${APP_DB}" < ./seed_demo.sql
