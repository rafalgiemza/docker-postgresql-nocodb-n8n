# Docker Deployment Guide

## 5 Essential Production Commands

### 1. START — Uruchom wszystkie serwisy
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```
Uruchamia n8n, NocoDB, PostgreSQL, Caddy w tle.

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

# Konkretny serwis (np. nocodb)
docker logs -f docker-nocodb-1

# Ostatnie 50 linii
docker logs docker-nocodb-1 | tail -50
```
`-f` oznacza "follow" (live streaming).

### 5. RESTART — Zrestartuj konkretny serwis
```bash
# Jeden serwis
docker restart docker-nocodb-1

# Kilka serwisów
docker restart docker-nocodb-1 docker-caddy-1

# Wszystkie
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart
```

---

## Stop/Restart Commands — Ważne rozróżnienia

### Zatrzymaj TYLKO konkretny serwis (bezpiecznie)
```bash
# Opcja 1: docker stop
docker stop docker-caddy-1

# Opcja 2: docker compose stop
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop caddy
```
Kontener zostaje (można go wznowić), inne serwisy działają.

### Zatrzymaj i usuń WSZYSTKIE kontenery
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
```
⚠️ Usuwa kontenery, ale **nie usuwa** volumes (dane są bezpieczne).

### Zrestartuj konkretny serwis (najczęściej używane)
```bash
docker restart docker-caddy-1
```
Idealny do szybkiego naprawienia serwisu.

### Porównanie
| Komenda | Wszystkie? | Usuwa kontenery? | Bezpieczna? |
|--------|-----------|------------------|-----------|
| `docker stop <name>` | ❌ Tylko jeden | ❌ Nie | ✅ Tak |
| `docker compose stop <name>` | ❌ Tylko jeden | ❌ Nie | ✅ Tak |
| `docker restart <name>` | ❌ Tylko jeden | ❌ Nie | ✅ Tak |
| `docker compose down` | ✅ Wszystkie | ✅ Tak | ⚠️ Ostrożnie |

**Pro tip:** Zawsze używaj `restart` lub `stop`, a nie `down`! 🛡️

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
docker exec docker-nocodb-1 env | grep NC_
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
| **PostgreSQL** | 5432 | (internal) | Database |
| **Caddy** | 80, 443 | 80, 443 | Reverse proxy + SSL |

---

## Useful URLs

- **Dev**: http://localhost:5678 (n8n), http://localhost:8081 (nocodb)
- **Prod**: https://n8n.giemza.dev, https://nocodb.giemza.dev

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

---

## Restart Policy & Healthcheck Audit (2026-07-14)

Post-mortem follow-up (see `post-mortem/logs.md`) checked whether every
long-running container recovers on its own after a crash or host restart.

- **Restart policy: already correct, no changes needed.** Every long-running
  service in `docker-compose.yml` already has `restart: unless-stopped`
  (postgres, n8n, n8n-runner, nocodb, minio, mongodb, librechat, caddy).
  `minio-init` is intentionally `restart: 'no'` — it's a one-shot bucket/user
  provisioning job, not a long-running service.
- **The real gap was missing healthchecks**, not restart policy: `caddy` and
  `n8n-runner` had none, so `docker compose ps` couldn't tell you they were
  unhealthy — only that the process hadn't exited. Both now have a
  `healthcheck:` block:
  - `n8n-runner`: `wget` against `http://localhost:5680/healthz`. The
    launcher bundled in the `n8nio/runners` image always starts its own
    health server on port 5680 — confirmed by inspecting a running
    container (`docker exec` + `ss -tlnp`), since the per-runner health
    server described in the launcher's own docs isn't actually exposed here.
  - `caddy`: `wget` against `http://127.0.0.1:2019/config/`, Caddy's admin
    API. `127.0.0.1`, not `localhost` — this image resolves `localhost` to
    `::1` first and the admin API only binds IPv4, so `wget` would hit
    nothing and report a false "unhealthy" (same pitfall as librechat's
    healthcheck).

Don't re-investigate restart policy for this reason again — it's already
audited and correct.

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
