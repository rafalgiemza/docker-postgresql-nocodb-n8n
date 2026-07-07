include .env
export

DC_CMD = docker compose -f docker-compose.yml -f docker-compose.prod.yml

.PHONY: up down ps logs migrate seed

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

backup:
	docker exec docker-postgres-1 pg_dump -U postgres -d $(APP_DB) > ./backups/backup_$(shell date +%F_%H%M%S).sql