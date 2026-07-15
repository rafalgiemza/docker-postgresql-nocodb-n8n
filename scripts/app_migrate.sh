#!/bin/bash
set -e
source .env

# init-data.sh (który normalnie tworzy te role) uruchamia się tylko raz, przy
# pierwszej inicjalizacji wolumenu Postgresa. Na środowiskach z już istniejącym
# wolumenem (np. VPS) rola dodana do init-data.sh później nigdy nie powstanie
# — stąd ten idempotentny "doszczep" tutaj, żeby schema.sql (REVOKE/GRANT na
# tych rolach) nie wywalał się na "role does not exist".
ensure_role() {
  local role="$1" password="$2"
  if [ -z "$role" ] || [ -z "$password" ]; then
    echo "⚠️  Skipping role setup: matching *_USER/*_PASSWORD not set in .env"
    return
  fi
  docker exec -i docker-postgres-1 psql -v ON_ERROR_STOP=1 \
    --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" <<-EOSQL
		DO \$\$
		BEGIN
		   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${role}') THEN
		      CREATE USER ${role} WITH PASSWORD '${password}';
		   END IF;
		END
		\$\$;
	EOSQL
  docker exec -i docker-postgres-1 psql -v ON_ERROR_STOP=1 \
    --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" \
    -c "GRANT CONNECT ON DATABASE ${APP_DB} TO ${role};"
  docker exec -i docker-postgres-1 psql -v ON_ERROR_STOP=1 \
    --username "${POSTGRES_USER}" --dbname "${APP_DB}" \
    -c "REVOKE CREATE ON SCHEMA public FROM ${role};"
}

echo "🔐 Ensuring restricted roles exist..."
ensure_role "${NOCODB_CRM_USER}" "${NOCODB_CRM_PASSWORD}"
ensure_role "${N8N_CRM_USER}" "${N8N_CRM_PASSWORD}"

echo "🚀 Run migrations for db ${APP_DB}..."
# Możesz użyć dedykowanego narzędzia (np. Atlas, Prisma, Liquibase) lub czystego psql:
docker exec -i docker-postgres-1 psql -v ON_ERROR_STOP=1 \
  --username "${APPDATA_OWNER_USER}" \
  --dbname "${APP_DB}" < ./schema.sql

echo "✅ Success."