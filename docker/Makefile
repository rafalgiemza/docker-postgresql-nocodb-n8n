include .env
export

DC_CMD = docker compose -f docker-compose.yml -f docker-compose.prod.yml
TS := $(shell date +%F_%H%M%S)

LATEST_TS := $(shell ls -1t ./backups/appdata_*.sql 2>/dev/null | head -n 1 | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}')
RESTORE_TS ?= $(LATEST_TS)

.PHONY: up down ps logs migrate seed seed-demo backup wire-apps

up:
	$(DC_CMD) up -d

down:
	$(DC_CMD) down

ps:
	$(DC_CMD) ps

logs:
	$(DC_CMD) logs -f

migrate:
	./app_migrate.sh

seed:
	./app_seed.sh

seed-demo:
	./app_seed_demo.sh

# Podłącza NocoDB (source appdata/crm + widoki) i n8n (credential appdata) —
# wymaga NC_API_TOKEN/N8N_API_KEY w .env (Krok 0 ręcznego bootstrapu, patrz
# docs/init-nocodb.md). Uruchom po `make migrate && make seed`.
wire-apps:
	./crm-wire-init.sh

backup:
	@mkdir -p ./backups
	docker exec docker-postgres-1 pg_dumpall -U postgres --roles-only > ./backups/roles_$(TS).sql
	docker exec docker-postgres-1 pg_dump -U postgres -d $(POSTGRES_DB) > ./backups/n8n_$(TS).sql
	docker exec docker-postgres-1 pg_dump -U postgres -d $(NC_DB) > ./backups/nocodb_meta_$(TS).sql
	docker exec docker-postgres-1 pg_dump -U postgres -d $(APP_DB) > ./backups/appdata_$(TS).sql
	docker run --rm -v docker_nocodb_storage:/data:ro -v $(CURDIR)/backups:/backup alpine tar -czf /backup/nocodb_attachments_$(TS).tar.gz -C /data .
	docker exec docker-mongodb-1 mongodump --archive --db=LibreChat --quiet > ./backups/mongo_$(TS).archive

restore:
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