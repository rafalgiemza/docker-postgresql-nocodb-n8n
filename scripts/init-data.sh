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

if [ -n "${RAG_DB_USER:-}" ] && [ -n "${RAG_DB_PASSWORD:-}" ] && [ -n "${RAG_DB:-}" ]; then
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
		CREATE USER ${RAG_DB_USER} WITH PASSWORD '${RAG_DB_PASSWORD}';
		CREATE DATABASE ${RAG_DB} OWNER ${RAG_DB_USER};
	EOSQL
else
	echo "SETUP INFO: No Environment variables given for the RAG DB user!"
fi

if [ -n "${APPDATA_OWNER_USER:-}" ] && [ -n "${APPDATA_OWNER_PASSWORD:-}" ] && [ -n "${APP_DB:-}" ]; then
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
		CREATE USER ${APPDATA_OWNER_USER} WITH PASSWORD '${APPDATA_OWNER_PASSWORD}';
		CREATE DATABASE ${APP_DB} OWNER ${APPDATA_OWNER_USER};
	EOSQL
else
	echo "SETUP INFO: No Environment variables given for the appdata owner user!"
fi

# Restricted role NocoDB connects with as an external Base. It only gets CONNECT here —
# NOT "GRANT ALL PRIVILEGES", unlike the old single-user setup. NocoDB is the tool used
# to design the `crm` schema itself (Creator/Editor separation is enforced by NocoDB's
# own collaborator roles, not by Postgres grants) — so this role gets CREATE+USAGE on
# `crm` directly here, and a default search_path so NocoDB's unqualified
# `CREATE TABLE "x" (...)` lands in `crm`, not `public`.
if [ -n "${NOCODB_CRM_USER:-}" ] && [ -n "${NOCODB_CRM_PASSWORD:-}" ] && [ -n "${APP_DB:-}" ]; then
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
		CREATE USER ${NOCODB_CRM_USER} WITH PASSWORD '${NOCODB_CRM_PASSWORD}';
		GRANT CONNECT ON DATABASE ${APP_DB} TO ${NOCODB_CRM_USER};
	EOSQL
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$APP_DB" <<-EOSQL
		REVOKE CREATE ON SCHEMA public FROM ${NOCODB_CRM_USER};
		CREATE SCHEMA IF NOT EXISTS crm AUTHORIZATION ${POSTGRES_USER};
		GRANT CREATE, USAGE ON SCHEMA crm TO ${NOCODB_CRM_USER};
		ALTER ROLE ${NOCODB_CRM_USER} IN DATABASE ${APP_DB} SET search_path TO crm;
	EOSQL
else
	echo "SETUP INFO: No Environment variables given for the NocoDB CRM user!"
fi

# Restricted role n8n connects with to run WF-6 ("Zatwierdź ofertę") against appdata.
# Separate from nocodb_crm_user (IMPLEMENTATION_PLAN.md §FAZA 3) so n8n and NocoDB stay
# distinguishable in pg_stat_activity/logs. USAGE/SELECT/UPDATE on crm.v_offer_builder
# (and REVOKE on schema `appdata`) are granted by schema.sql section 15 once that schema
# exists, since it can't be created here (init-data.sh runs once, before any migration,
# on a fresh Postgres volume).
if [ -n "${N8N_CRM_USER:-}" ] && [ -n "${N8N_CRM_PASSWORD:-}" ] && [ -n "${APP_DB:-}" ]; then
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
		CREATE USER ${N8N_CRM_USER} WITH PASSWORD '${N8N_CRM_PASSWORD}';
		GRANT CONNECT ON DATABASE ${APP_DB} TO ${N8N_CRM_USER};
	EOSQL
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$APP_DB" <<-EOSQL
		REVOKE CREATE ON SCHEMA public FROM ${N8N_CRM_USER};
	EOSQL
else
	echo "SETUP INFO: No Environment variables given for the n8n CRM user!"
fi