# Hard reset środowiska Docker (n8n + NocoDB + Postgres)

Procedura do pełnego zresetowania środowiska tak, jakby repo zostało właśnie sklonowane na nowym VPS. **Kasuje wszystkie dane**: bazę `appdata`, `n8n`, `nocodb` (workflowy, credentiale, connections), oraz wszystkie hasła w `.env`.

Przed startem sprawdź, czy nie tracisz czegoś nieodtwarzalnego:
- workflowy n8n wyeksportowane do `n8n-workflows/*.json` (jeśli robiłeś zmiany w UI od ostatniego exportu — wyeksportuj je teraz, patrz [`docs/offer-builder.md`](offer-builder.md) §4)
- konfiguracja NocoDB (source appdata/crm + widoki Kanban/Grid/Calendar) i credential n8n→appdata są teraz odtwarzane automatycznie przez `make wire-apps` (`scripts/crm-wire-init.sh`) — patrz krok 7-8 niżej i `docs/init-nocodb.md`/`docs/init-n8n.md`. Zostaje jeden manualny, jednorazowy krok: bootstrap kont (super-admin NocoDB, owner n8n) + wygenerowanie API tokenów.

## Kroki

```bash
# (uruchamiane z katalogu repo)

# 1. Zatrzymaj i skasuj kontenery + WOLUMENY (usuwa wszystkie dane)
docker compose down -v --remove-orphans

# 2. Wygeneruj świeży .env z nowymi losowymi sekretami
#    (spyta o nadpisanie istniejącego .env — potwierdź "y")
./scripts/generate-env.sh

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

# 7. Krok 0 (ręcznie, jednorazowo — patrz docs/init-nocodb.md i docs/init-n8n.md):
#    - NocoDB: Sign Up jako super-admin, potem Account → API Tokens → wklej jako NC_API_TOKEN w .env
#    - n8n: dokończ setup wizard (owner account), potem Settings → API → Create API Key → wklej jako N8N_API_KEY w .env

# 8. Podłącz NocoDB (source appdata/crm + widoki Kanban/Grid/Calendar) i n8n
#    (credential appdata) automatycznie:
make wire-apps
```

**Kolejność jest kluczowa**: `scripts/generate-env.sh` musi się wykonać PRZED `docker compose up`. Hasła z `.env` są wpisywane do ról Postgresa tylko raz — przy pierwszej inicjalizacji pustego wolumenu (`docker-entrypoint-initdb.d` uruchamia się jednorazowo, tylko na czystych danych). Jeśli wygenerujesz nowy `.env` na już istniejącym wolumenie, nowe hasła nie zostaną zastosowane do ról w bazie — powstanie rozjazd między `.env` a rzeczywistymi hasłami w Postgresie.

## Po resecie — co trzeba odtworzyć ręcznie

Po kroku 7-8 powyżej (`make wire-apps`), NocoDB ma już podłączony source do `appdata`/`crm` + widoki (Kanban etapów, listy/kalendarze "moje zadania" per osoba, widok notatek), a n8n ma już credential `appdata (n8n_crm_user)`. Zostaje:

n8n:
- zaimportuj workflow z `n8n-workflows/*.json` (Workflows → Import from File)
- podepnij credential `appdata (n8n_crm_user)` pod odpowiednie node'y i aktywuj workflow

NocoDB:
- odtwórz widok „Offer Builder" wg [`docs/offer-builder.md`](offer-builder.md) §5
- przypisz realnym osobom role NocoDB (Creator/Editor/Viewer) w UI — świadomie poza zakresem automatyzacji, patrz `docs/init-nocodb.md`

Jeśli `make wire-apps` zawiedzie (np. NocoDB/n8n API się zmieniło w nowszej wersji): ręczne kroki opisane w `docs/init-nocodb.md` i `docs/init-n8n.md` wciąż działają jako fallback — dodaj connection ręcznie (host `postgres`, port `5432`, database `appdata`, schema `crm`, user `nocodb_crm_user`, hasło z `.env`), i credential w n8n analogicznie.

## Weryfikacja że baza faktycznie istnieje po resecie

```bash
# Bazy
docker exec docker-postgres-1 psql -U postgres -c "\l"

# Schematy w appdata (powinny być: appdata, crm, public)
docker exec docker-postgres-1 psql -U postgres -d appdata -c "\dn"

# Widoki w crm (powinno być 9: v_audit_scores, v_offer_builder, v_offer_goals,
# v_opportunity_dates, v_opportunity_notes, v_pipeline, v_pricing, v_tasks, v_testimonials)
docker exec docker-postgres-1 psql -U postgres -d appdata -c "\dv crm.*"

# Test logowania rolą używaną przez NocoDB
export $(grep -E '^(NOCODB_CRM_USER|NOCODB_CRM_PASSWORD|APP_DB)=' .env | xargs)
docker exec -e PGPASSWORD="$NOCODB_CRM_PASSWORD" docker-postgres-1 \
  psql -h localhost -U "$NOCODB_CRM_USER" -d "$APP_DB" -c "SELECT 1;"
```
