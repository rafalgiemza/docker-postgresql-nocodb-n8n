include .env
export

DC_CMD = docker compose -f docker-compose.yml -f docker-compose.prod.yml
TS := $(shell date +%F_%H%M%S)

.PHONY: up down ps logs migrate seed seed-demo backup

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

backup:
	@mkdir -p ./backups
	docker exec docker-postgres-1 pg_dumpall -U postgres --roles-only > ./backups/roles_$(TS).sql
	docker exec docker-postgres-1 pg_dump -U postgres -d $(POSTGRES_DB) > ./backups/n8n_$(TS).sql
	docker exec docker-postgres-1 pg_dump -U postgres -d $(NC_DB) > ./backups/nocodb_meta_$(TS).sql
	docker exec docker-postgres-1 pg_dump -U postgres -d $(APP_DB) > ./backups/appdata_$(TS).sql
	docker run --rm -v docker_nocodb_storage:/data:ro -v $(CURDIR)/backups:/backup alpine tar -czf /backup/nocodb_attachments_$(TS).tar.gz -C /data .