# Docker Deployment Guide

## 5 Essential Production Commands

### 1. START — Uruchom wszystkie serwisy
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```
Uruchamia n8n, NocoDB, Planka, PostgreSQL, Caddy w tle.

### 2. STOP — Zatrzymaj wszystkie serwisy
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
```
Zatrzymuje i usuwa kontenery (nie usuwa volumes/danych).

### 3. STATUS — Sprawdź czy kontenery żyją
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```
Pokazuje status każdego kontenera (Up, Down, Restarting).

### 4. LOGI — Śledź logi w time
```bash
# Wszystkie serwisy
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f

# Konkretny serwis (np. planka)
docker logs -f docker-planka-1

# Ostatnie 50 linii
docker logs docker-planka-1 | tail -50
```
`-f` oznacza "follow" (live streaming).

### 5. RESTART — Zrestartuj konkretny serwis
```bash
# Jeden serwis
docker restart docker-planka-1

# Kilka serwisów
docker restart docker-planka-1 docker-caddy-1

# Wszystkie
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart
```

---

## Debugging & Maintenance

### Resource Usage
```bash
docker stats --no-stream
```
Pokazuje RAM, CPU każdego kontenera.

### Wejdź do bazy danych
```bash
docker exec -it docker-postgres-1 psql -U postgres
```
Interaktywna konsola PostgreSQL.

### Sprawdź zmienne środowiska
```bash
docker exec docker-planka-1 env | grep PLANKA
```

### Backup bazy danych
```bash
docker exec docker-postgres-1 pg_dump -U postgres -d n8n > backup_n8n.sql
```

### Wyczyść nieużywane zasoby
```bash
docker system prune -a --volumes
```
⚠️ Usuwa wszystkie nieużywane kontenery, obrazy, volumy.

---

## Serwisy

| Serwis | Port (dev) | Port (prod) | Opis |
|--------|-----------|-----------|------|
| **n8n** | 5678 | https://n8n.giemza.dev | Workflow automation |
| **NocoDB** | 8081 | https://nocodb.giemza.dev | Database UI |
| **Planka** | 3000 | https://planka.giemza.dev | Kanban board |
| **PostgreSQL** | 5432 | (internal) | Database |
| **Caddy** | 80, 443 | 80, 443 | Reverse proxy + SSL |

---

## Useful URLs

- **Dev**: http://localhost:5678 (n8n), http://localhost:8081 (nocodb), http://localhost:3000 (planka)
- **Prod**: https://n8n.giemza.dev, https://nocodb.giemza.dev, https://planka.giemza.dev

---

## First Setup

1. **Ustaw zmienne w `.env`**
   ```bash
   cp .env.example .env
   # Edytuj .env i wstaw rzeczywiste wartości
   ```

2. **Uruchom serwisy**
   ```bash
   docker compose up -d  # dev
   # lub
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d  # prod
   ```

3. **Czekaj na inicjalizację bazy** (~2-3 minuty)
   ```bash
   docker compose ps
   # Wszystkie powinny być "healthy"
   ```

4. **Dla Planki: stwórz admin usera**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm planka npm run db:create-admin-user
   ```

---

## Troubleshooting

### Error 525 (Cloudflare)
```bash
# Usuń stare certyfikaty i wymuś regenerację
docker compose -f docker-compose.yml -f docker-compose.prod.yml down caddy
rm -rf caddy_data caddy_config
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d caddy
```

### Kontener restartuje się
```bash
docker logs <container_name> | tail -50
```

### Baza danych nie inicjalizuje się
```bash
# Usuń volume i zrestartuj
docker volume rm docker_db_storage
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgres
```
