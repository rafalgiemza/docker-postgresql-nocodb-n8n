# Podłączenie n8n do Postgresa (node PostgreSQL)

n8n nigdy nie łączy się jako superuser — używa osobnej, ograniczonej roli.

## 1. Pobranie danych logowania

Na hoście, w katalogu `docker/`:

```bash
grep -E "^POSTGRES_(NON_ROOT_USER|NON_ROOT_PASSWORD|DB)=" .env
```

## 2. Konfiguracja credentiala w n8n (node Postgres)

- **Host**: `postgres` (nazwa serwisu w sieci docker-compose)
- **Port**: `5432`
- **Database**: wartość `POSTGRES_DB`
- **User**: wartość `POSTGRES_NON_ROOT_USER`
- **Password**: wartość `POSTGRES_NON_ROOT_PASSWORD`
- **SSL**: wyłączone (ruch wewnątrz sieci docker)

Jeśli n8n łączy się spoza sieci compose (inny host / zdalnie), host/port będą inne — do ustalenia osobno.
