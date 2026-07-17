include .env
export

.DEFAULT_GOAL := help

DC_CMD = docker compose -f docker-compose.yml

LATEST_TS := $(shell ls -1t ./backups/appdata_*.sql 2>/dev/null | head -n 1 | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}')
RESTORE_TS ?= $(LATEST_TS)

.PHONY: help init-env config up down restart pull ps logs migrate seed seed-demo backup backup-prune restore wire-apps add-rag-db

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' Makefile | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

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
	$(DC_CMD) ps

logs: ## Tail logs for all services (Ctrl+C to stop)
	$(DC_CMD) logs -f

migrate: ## Apply appdata/appdata_schema.sql to appdata (see app_migrate.sh)
	./scripts/app_migrate.sh

seed: ## Load reference data (pricing tiers, testimonials, users)
	./scripts/app_seed.sh

seed-demo: ## Load one demo offer end-to-end (re-runnable)
	./scripts/app_seed_demo.sh

# Podłącza NocoDB (source appdata/crm + widoki) i n8n (credential appdata) —
# wymaga NC_API_TOKEN/N8N_API_KEY w .env (Krok 0 ręcznego bootstrapu, patrz
# docs/init-nocodb.md). Uruchom po `make migrate && make seed`.
wire-apps: ## Wire NocoDB/n8n to appdata/crm after a hard-reset
	./scripts/crm-wire-init.sh

# Jednorazowe dodanie bazy RAG na już działającym Postgresie — init-data.sh
# odpala się tylko przy świeżym, pustym wolumenie, więc na istniejącej
# instancji (np. VPS) trzeba to donieść ręcznie. Wymaga
# RAG_DB_USER/RAG_DB_PASSWORD/RAG_DB w .env. Idempotentne — bezpieczne do
# odpalenia ponownie, jeśli user/baza już istnieją.
add-rag-db: ## One-time: add the RAG database to an already-running Postgres
	docker exec -i docker-postgres-1 psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c "CREATE USER $(RAG_DB_USER) WITH PASSWORD '$(RAG_DB_PASSWORD)';" || true
	docker exec -i docker-postgres-1 psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c "CREATE DATABASE $(RAG_DB) OWNER $(RAG_DB_USER);" || true

backup: ## Dump all DBs + NocoDB attachments to ./backups and push offsite via restic
	./backup/backup.sh

backup-prune: ## Run backup + prune old restic snapshots (same as the daily cron job)
	./backup/backup.sh --prune

restore: ## Restore from the latest (or RESTORE_TS=<ts>) local dump in ./backups
	@if [ -z "$(RESTORE_TS)" ]; then \
		echo "❌ Błąd: Nie znaleziono żadnych plików backupu w folderze ./backups!"; \
		exit 1; \
	fi
	@echo "🚀 Rozpoczynam przywracanie z backupu: $(RESTORE_TS)"
	
	@echo "📦 1/7 Podnoszę środowisko, aby uruchomić bazy danych..."
	$(DC_CMD) up -d
	@echo "⏳ Czekam 15 sekund, aż bazy danych będą gotowe na przyjmowanie połączeń..."
	@sleep 15

	@echo "🗄️ 2/7 Tworzę bazy danych na nowym serwerze (ignorując błędy jeśli już istnieją)..."
	@docker exec docker-postgres-1 psql -U postgres -c "CREATE DATABASE $(POSTGRES_DB);" || true
	@docker exec docker-postgres-1 psql -U postgres -c "CREATE DATABASE $(NC_DB);" || true
	@docker exec docker-postgres-1 psql -U postgres -c "CREATE DATABASE $(APP_DB);" || true

	@echo "🔑 3/7 Przywracanie globalnych ról..."
	@cat ./backups/roles_$(RESTORE_TS).sql | docker exec -i docker-postgres-1 psql -U postgres || true

	@echo "💾 4/7 Przywracanie struktury i danych z plików SQL..."
	@echo "   -> Wgrywam bazę n8n..."
	cat ./backups/n8n_$(RESTORE_TS).sql | docker exec -i docker-postgres-1 psql -U postgres -d $(POSTGRES_DB)
	@echo "   -> Wgrywam bazę NocoDB Meta..."
	cat ./backups/nocodb_meta_$(RESTORE_TS).sql | docker exec -i docker-postgres-1 psql -U postgres -d $(NC_DB)
	@echo "   -> Wgrywam bazę AppData..."
	cat ./backups/appdata_$(RESTORE_TS).sql | docker exec -i docker-postgres-1 psql -U postgres -d $(APP_DB)

	@echo "📂 5/7 Wypakowuję archiwum załączników NocoDB bezpośrednio do wolumenu..."
	docker run --rm -v docker_nocodb_storage:/data -v $(CURDIR)/backups:/backup alpine tar -xzf /backup/nocodb_attachments_$(RESTORE_TS).tar.gz -C /data

	@echo "🍃 6/7 Przywracanie bazy MongoDB (LibreChat)..."
	@if [ -f "./backups/mongo_$(RESTORE_TS).archive" ]; then \
		cat ./backups/mongo_$(RESTORE_TS).archive | docker exec -i docker-mongodb-1 mongorestore --archive --drop; \
		echo "   -> MongoDB przywrócone."; \
	else \
		echo "   -> Brak pliku mongo_$(RESTORE_TS).archive. Pomijam ten krok."; \
	fi

	@echo "🔄 7/7 Twardy restart kontenerów, by zaczytały przywrócone dane..."
	$(DC_CMD) restart
	@echo "✅ Success!"