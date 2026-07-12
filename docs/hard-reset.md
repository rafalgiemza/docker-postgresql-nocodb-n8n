# Hard reset środowiska Docker (n8n + NocoDB + Postgres)

Procedura do pełnego zresetowania środowiska tak, jakby repo zostało właśnie sklonowane na nowym VPS. **Kasuje wszystkie dane**: bazę `appdata`, `n8n`, `nocodb` (workflowy, credentiale, connections), oraz wszystkie hasła w `.env`.

Przed startem sprawdź, czy nie tracisz czegoś nieodtwarzalnego:
- workflowy n8n wyeksportowane do `docker/n8n-workflows/*.json` (jeśli robiłeś zmiany w UI od ostatniego exportu — wyeksportuj je teraz, patrz `docker/README.md` §4)
- konfiguracja NocoDB (widoki, connections) — nieskryptowana, trzeba będzie odtworzyć ręcznie w UI

## Kroki

```bash
cd docker

# 1. Zatrzymaj i skasuj kontenery + WOLUMENY (usuwa wszystkie dane)
docker compose down -v --remove-orphans

# 2. Wygeneruj świeży .env z nowymi losowymi sekretami
#    (spyta o nadpisanie istniejącego .env — potwierdź "y")
./generate-env.sh

# 3. Sprawdź .env pod kątem wartości NIE-sekretnych — generate-env.sh
#    losuje tylko placeholdery "change...", więc hosty trzeba
#    zweryfikować ręcznie: N8N_HOST, NC_HOST, WEBHOOK_URL
#    (na UAT: giemza.dev; na prod dopiero po DNS od klienta, patrz
#    .ai/IMPLEMENTATION_PLAN.md FAZA 7)

# 4. (opcjonalnie, głębiej) usuń nieużywane obrazy/sieci/cache budowania
docker system prune -af

# 5. Odpal kontenery od zera — init-data.sh użyje NOWYCH haseł z .env
docker compose up -d
docker compose ps    # poczekaj aż wszystko "healthy"

# 6. Odtwórz schemat bazy + dane referencyjne
make migrate
make seed
# opcjonalnie, do testów Offer Buildera:
make seed-demo
```

**Kolejność jest kluczowa**: `generate-env.sh` musi się wykonać PRZED `docker compose up`. Hasła z `.env` są wpisywane do ról Postgresa tylko raz — przy pierwszej inicjalizacji pustego wolumenu (`docker-entrypoint-initdb.d` uruchamia się jednorazowo, tylko na czystych danych). Jeśli wygenerujesz nowy `.env` na już istniejącym wolumenie, nowe hasła nie zostaną zastosowane do ról w bazie — powstanie rozjazd między `.env` a rzeczywistymi hasłami w Postgresie.

## Po resecie — co trzeba odtworzyć ręcznie

n8n będzie zupełnie pusty:
- odtwórz credential Postgres w n8n UI (host `postgres`, port `5432`, baza z `APP_DB`, user/hasło z `N8N_CRM_USER`/`N8N_CRM_PASSWORD` w nowym `.env`) — patrz `docker/README.md` §2
- zaimportuj workflow z `docker/n8n-workflows/*.json` (Workflows → Import from File)
- podepnij credential pod odpowiednie node'y i aktywuj workflow

NocoDB będzie bez połączenia do `appdata`:
- dodaj connection od nowa: host `postgres`, port `5432`, database `appdata`, schema `crm`, user `nocodb_crm_user`, hasło z nowego `.env` (`NOCODB_CRM_PASSWORD`)
- odtwórz widok „Offer Builder" wg `docker/README.md` §5

## Weryfikacja że baza faktycznie istnieje po resecie

```bash
# Bazy
docker exec docker-postgres-1 psql -U postgres -c "\l"

# Schematy w appdata (powinny być: appdata, crm, public)
docker exec docker-postgres-1 psql -U postgres -d appdata -c "\dn"

# Widoki w crm (powinno być 8: v_audit_scores, v_offer_builder, v_offer_goals,
# v_opportunity_dates, v_pipeline, v_pricing, v_tasks, v_testimonials)
docker exec docker-postgres-1 psql -U postgres -d appdata -c "\dv crm.*"

# Test logowania rolą używaną przez NocoDB
export $(grep -E '^(NOCODB_CRM_USER|NOCODB_CRM_PASSWORD|APP_DB)=' .env | xargs)
docker exec -e PGPASSWORD="$NOCODB_CRM_PASSWORD" docker-postgres-1 \
  psql -h localhost -U "$NOCODB_CRM_USER" -d "$APP_DB" -c "SELECT 1;"
```
