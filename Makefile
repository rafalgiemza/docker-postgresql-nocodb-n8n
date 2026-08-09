-include .env
export

.DEFAULT_GOAL := help

DC_CMD = docker compose -f docker-compose.yml

LATEST_TS := $(shell ls -1t ./backups/appdata_*.sql 2>/dev/null | head -n 1 | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}')
RESTORE_TS ?= $(LATEST_TS)

.PHONY: help init init-env config up down restart pull ps versions logs migrate dump-appdata-schema seed seed-demo backup backup-prune restore wire-apps init-schema init-appdata-db add-rag-db

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' Makefile | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

init: ## First-time setup on a fresh server: generate .env, prompt for OpenRouter key + domain
	./scripts/init.sh

init-env: ## Create .env from .env.example with randomly generated secrets
	./scripts/generate-env.sh

config: ## Validate the merged compose config (fragments/*.yml via include:)
	$(DC_CMD) config --quiet

up: ## Start the full stack in the background
	$(DC_CMD) up -d

down: ## Stop and remove the stack (named volumes are preserved)
	$(DC_CMD) down

restart: ## Restart all containers
	$(DC_CMD) restart

pull: ## Pull the latest images for all services
	$(DC_CMD) pull

ps: ## Show container status
	$(DC_CMD) ps --format "table {{.ID}}\t{{.Name}}\t{{.Status}}"

versions: ## Print actual running versions of all services (not just .env tags)
	./scripts/versions.sh

logs: ## Tail logs for all services (Ctrl+C to stop)
	$(DC_CMD) logs -f

migrate: ## Apply appdata/appdata_schema.sql to appdata (see app_migrate.sh)
	./scripts/app_migrate.sh

dump-appdata-schema: ## Dump current schema of a running appdata DB into appdata/appdata_schema.sql
	docker exec -i docker-postgres-1 pg_dump -U $(POSTGRES_USER) -d $(APP_DB) --schema-only > ./appdata/appdata_schema.sql
	@echo "✅ Zapisano appdata/appdata_schema.sql"

seed: ## Load reference data (pricing tiers, testimonials, users)
	./scripts/app_seed.sh

seed-demo: ## Load one demo offer end-to-end (re-runnable)
	./scripts/app_seed_demo.sh

# Podłącza NocoDB (source appdata/crm + widoki) i n8n (credential appdata) —
# wymaga NC_API_TOKEN/N8N_API_KEY w .env (Krok 0 ręcznego bootstrapu, patrz
# docs/init-nocodb.md). Uruchom po `make migrate && make seed`.
wire-apps: ## Wire NocoDB/n8n to appdata/crm after a hard-reset
	./scripts/crm-wire-init.sh

# Tworzy 16 tabel CRM + relacje w NocoDB przez Meta API — wymaga `make wire-apps`
# najpierw. Patrz naglowek scripts/init-schema.py po pelny kontekst.
init-schema: ## Create the full CRM schema (16 tables + relations) in NocoDB — run after wire-apps
	./scripts/init-schema.sh

init-data: 
	 # 1. Sanity check - serwis widzi plik i ma NC_API_TOKEN/NC_CRM_BASE_ID?
	curl -s http://localhost:8001/health

	# 2. Dry-run - tylko liczba rekordów, bez zapisu
	curl -s -X POST "http://localhost:8001/seed?dry_run=true"

	# 3. Właściwy seed
	curl -s -X POST "http://localhost:8001/seed?dry_run=false"

# Jednorazowe (re)utworzenie bazy appdata + ról appdata_owner/nocodb_crm_user/
# n8n_crm_user + pustego schematu crm — to samo co init-data.sh robi na
# świeżym wolumenie Postgresa, ale ręcznie, na już działającej instancji
# (np. po `DROP DATABASE appdata` albo gdy .env nie miał tych zmiennych przy
# pierwszym starcie kontenera). Świadomie BEZ appdata_schema.sql — ten plik to
# zdjęcie starego, przedwersyjnego (v2) układu tabel; tabele v3 tworzy
# `make init-schema` przez NocoDB Meta API, nie SQL. Idempotentne.
init-appdata-db: ## One-time: (re)create the appdata database + roles/crm schema on an already-running Postgres
	docker exec -i docker-postgres-1 psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c "CREATE USER $(APPDATA_OWNER_USER) WITH PASSWORD '$(APPDATA_OWNER_PASSWORD)';" || true
	docker exec -i docker-postgres-1 psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c "CREATE DATABASE $(APP_DB) OWNER $(APPDATA_OWNER_USER);" || true
	docker exec -i docker-postgres-1 psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c "CREATE USER $(NOCODB_CRM_USER) WITH PASSWORD '$(NOCODB_CRM_PASSWORD)';" || true
	docker exec -i docker-postgres-1 psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c "GRANT CONNECT ON DATABASE $(APP_DB) TO $(NOCODB_CRM_USER);" || true
	docker exec -i docker-postgres-1 psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c "CREATE USER $(N8N_CRM_USER) WITH PASSWORD '$(N8N_CRM_PASSWORD)';" || true
	docker exec -i docker-postgres-1 psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c "GRANT CONNECT ON DATABASE $(APP_DB) TO $(N8N_CRM_USER);" || true
	docker exec -i docker-postgres-1 psql -U $(POSTGRES_USER) -d $(APP_DB) -c "REVOKE CREATE ON SCHEMA public FROM $(NOCODB_CRM_USER); REVOKE CREATE ON SCHEMA public FROM $(N8N_CRM_USER); CREATE SCHEMA IF NOT EXISTS crm AUTHORIZATION $(POSTGRES_USER); GRANT CREATE, USAGE ON SCHEMA crm TO $(NOCODB_CRM_USER); ALTER ROLE $(NOCODB_CRM_USER) IN DATABASE $(APP_DB) SET search_path TO crm;"
	@echo "✅ appdata + role gotowe. Dalej: make init-schema"

# Jednorazowe dodanie bazy RAG na już działającym Postgresie — init-data.sh
# odpala się tylko przy świeżym, pustym wolumenie, więc na istniejącej
# instancji (np. VPS) trzeba to donieść ręcznie. Wymaga
# RAG_DB_USER/RAG_DB_PASSWORD/RAG_DB w .env. Idempotentne — bezpieczne do
# odpalenia ponownie, jeśli user/baza już istnieją.
add-rag-db: ## One-time: add the RAG database to an already-running Postgres
	docker exec -i docker-postgres-1 psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c "CREATE USER $(RAG_DB_USER) WITH PASSWORD '$(RAG_DB_PASSWORD)';" || true
	docker exec -i docker-postgres-1 psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c "CREATE DATABASE $(RAG_DB) OWNER $(RAG_DB_USER);" || true

backup: ## Dump all DBs + NocoDB/SeaweedFS volumes to ./backups and push offsite via restic
	./backup/backup.sh

backup-prune: ## Run backup + prune old restic snapshots (same as the daily cron job)
	./backup/backup.sh --prune

restore: ## Restore from the latest (or RESTORE_TS=<ts>) local dump in ./backups
	./backup/restore.sh "$(RESTORE_TS)"
