#!/bin/bash
set -e;


if [ -n "${POSTGRES_NON_ROOT_USER:-}" ] && [ -n "${POSTGRES_NON_ROOT_PASSWORD:-}" ]; then
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
		CREATE USER ${POSTGRES_NON_ROOT_USER} WITH PASSWORD '${POSTGRES_NON_ROOT_PASSWORD}';
		GRANT ALL PRIVILEGES ON DATABASE ${POSTGRES_DB} TO ${POSTGRES_NON_ROOT_USER};
		GRANT CREATE ON SCHEMA public TO ${POSTGRES_NON_ROOT_USER};
	EOSQL
else
	echo "SETUP INFO: No Environment variables given for the n8n user!"
fi

if [ -n "${NC_DB_USER:-}" ] && [ -n "${NC_DB_PASSWORD:-}" ] && [ -n "${NC_DB:-}" ]; then
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
		CREATE USER ${NC_DB_USER} WITH PASSWORD '${NC_DB_PASSWORD}';
		CREATE DATABASE ${NC_DB} OWNER ${NC_DB_USER};
	EOSQL
else
	echo "SETUP INFO: No Environment variables given for the NocoDB user!"
fi

if [ -n "${APP_DB_USER:-}" ] && [ -n "${APP_DB_PASSWORD:-}" ] && [ -n "${APP_DB:-}" ]; then
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
		CREATE USER ${APP_DB_USER} WITH PASSWORD '${APP_DB_PASSWORD}';
		CREATE DATABASE ${APP_DB} OWNER ${APP_DB_USER};
	EOSQL
else
	echo "SETUP INFO: No Environment variables given for the app database user!"
fi

if [ -n "${PLANKA_DB_USER:-}" ] && [ -n "${PLANKA_DB_PASSWORD:-}" ] && [ -n "${PLANKA_DB:-}" ]; then
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
		CREATE USER ${PLANKA_DB_USER} WITH PASSWORD '${PLANKA_DB_PASSWORD}';
		CREATE DATABASE ${PLANKA_DB} OWNER ${PLANKA_DB_USER};
	EOSQL
else
	echo "SETUP INFO: No Environment variables given for the Planka database user!"
fi

if [ -n "${APP_DB_USER:-}" ] && [ -n "${APP_DB_PASSWORD:-}" ] && [ -n "${APP_DB:-}" ] && [ -f /docker-entrypoint-initdb.d/schema.sql ]; then
	echo "SETUP INFO: Running schema.sql on ${APP_DB} database..."
	psql -v ON_ERROR_STOP=1 --username "${APP_DB_USER}" --dbname "${APP_DB}" -f /docker-entrypoint-initdb.d/schema.sql
else
	if [ ! -f /docker-entrypoint-initdb.d/schema.sql ]; then
		echo "SETUP INFO: schema.sql file not found, skipping database schema initialization!"
	fi
fi