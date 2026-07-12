#!/bin/bash
set -e
source .env

echo "🚀 Run migrations for db ${APP_DB}..."
# Możesz użyć dedykowanego narzędzia (np. Atlas, Prisma, Liquibase) lub czystego psql:
docker exec -i docker-postgres-1 psql -v ON_ERROR_STOP=1 \
  --username "${APPDATA_OWNER_USER}" \
  --dbname "${APP_DB}" < ./schema.sql

echo "✅ Success."