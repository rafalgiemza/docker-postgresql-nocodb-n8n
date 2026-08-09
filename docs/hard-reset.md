# Hard reset środowiska Docker (n8n + NocoDB + Postgres)

Procedura do pełnego zresetowania środowiska tak, jakby repo zostało właśnie sklonowane na nowym VPS. **Kasuje wszystkie dane**: bazę `appdata`, `n8n`, `nocodb` (workflowy, credentiale, connections), oraz wszystkie hasła w `.env`.

Przed startem sprawdź, czy nie tracisz czegoś nieodtwarzalnego: workflowy n8n zaimportowane/zmienione w UI od ostatniego exportu (Workflows → Download) i widoki/dane w NocoDB, które nie żyją w Postgresie (np. ręcznie klikane ustawienia UI).

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

# 5. Odpal kontenery od zera — init-data.sh (docker-entrypoint-initdb.d) użyje
#    NOWYCH haseł z .env i utworzy role appdata_owner/nocodb_crm_user/
#    n8n_crm_user + pusty schemat appdata.crm + bazę rag_db
docker compose up -d
docker compose ps    # poczekaj aż wszystko "healthy"
```

**Kolejność jest kluczowa**: `scripts/generate-env.sh` musi się wykonać PRZED `docker compose up`. Hasła z `.env` są wpisywane do ról Postgresa tylko raz — przy pierwszej inicjalizacji pustego wolumenu (`docker-entrypoint-initdb.d` uruchamia się jednorazowo, tylko na czystych danych). Jeśli wygenerujesz nowy `.env` na już istniejącym wolumenie, nowe hasła nie zostaną zastosowane do ról w bazie — powstanie rozjazd między `.env` a rzeczywistymi hasłami w Postgresie.

## Krok 0 — jednorazowy bootstrap kont (ręcznie, raz na hard-reset)

Nieodtwarzalne automatycznie — jednorazowy bootstrap kont admina, kruchy i wersja-zależny, świadomie zostawiony jako ręczny krok (patrz nagłówek `scripts/crm-wire-init.sh` w historii repo dla uzasadnienia tej decyzji).

1. **NocoDB UI** (`$NC_HOST`) → **Sign Up** (pierwsza osoba, która się zaloguje, zostaje super-adminem) → utwórz bazę (np. „CoAction CRM").
2. W tej bazie → **Create External Source** (Postgres), żeby CRM realnie żył w `appdata`/`crm`, nie w wewnętrznej bazie NocoDB:
   - Host: `postgres`, Port: `5432`
   - Database: wartość `APP_DB` (domyślnie `appdata`)
   - Schema: `crm`
   - User/Password: `NOCODB_CRM_USER`/`NOCODB_CRM_PASSWORD` z `.env`
   - SSL: wyłączone (ruch wewnątrz sieci docker-compose)

   Bez tego kroku `make init-schema` tworzy tabele w wewnętrznej bazie NocoDB zamiast w `appdata` — poza `make backup`, poza zasięgiem `n8n_crm_user`. Patrz nagłówek `scripts/init-schema.py` (`resolve_source()`).
3. Konto → **API Tokens** → utwórz → wklej jako `NC_API_TOKEN` w `.env`.
4. Zanotuj id bazy z URL NocoDB (`/api/v2/meta/bases/<id>` albo widoczne w pasku adresu po wejściu w bazę) → wklej jako `NC_CRM_BASE_ID` w `.env`.
5. **n8n UI** (`$N8N_HOST`) → dokończ setup wizard (owner account) — bez tego n8n jest niedostępne. `N8N_API_KEY` (Settings → API → Create API Key) jest opcjonalny — żaden obecny skrypt go nie wymaga, przydaje się tylko do ręcznego zarządzania n8n przez jego własne API.

## Odtworzenie schematu CRM i danych

```bash
# 6. Utwórz 16 tabel CRM + relacje w NocoDB (Meta API), od razu z upgrade
#    pól relacji do formatu v3 — patrz nagłówek scripts/init-schema.py
make init-schema

# 7. Zaseeduj leads/companies/participants z historycznego Excela (CRM)
#    przez seed-service — patrz seed-service/README.md
make init-data

# 8. Opcjonalnie, do testów: zaseeduj pozostałe 13 tabel (meetings/offers/
#    tasks/...) danymi testowymi przez NocoDB API — NIE do produkcji
make seed-extra
```

## Po resecie — co trzeba odtworzyć ręcznie

n8n:
- zaimportuj workflowy z `docs/archive/fable/W*.json` (Workflows → Import from File) — patrz `file-renderer-service/README.md` dla przykładu (W9)
- podepnij odpowiednie credentiale pod node'y i aktywuj workflow

NocoDB:
- odtwórz potrzebne widoki (Kanban/Grid/Calendar per osoba) w UI — `scripts/init-schema.py` ich nie tworzy, patrz jego nagłówek sekcja "CZEGO TEN SKRYPT NIE ROBI"
- przypisz realnym osobom role NocoDB (Creator/Editor/Viewer) w UI — świadomie poza zakresem automatyzacji

## Weryfikacja że baza faktycznie istnieje po resecie

```bash
# Bazy
docker exec docker-postgres-1 psql -U postgres -c "\l"

# Schematy w appdata (powinny być: appdata, crm, public)
docker exec docker-postgres-1 psql -U postgres -d appdata -c "\dn"

# Tabele CRM w schemacie crm (16 tabel utworzonych przez make init-schema)
docker exec docker-postgres-1 psql -U postgres -d appdata -c "\dt crm.*"

# Test logowania rolą używaną przez NocoDB
export $(grep -E '^(NOCODB_CRM_USER|NOCODB_CRM_PASSWORD|APP_DB)=' .env | xargs)
docker exec -e PGPASSWORD="$NOCODB_CRM_PASSWORD" docker-postgres-1 \
  psql -h localhost -U "$NOCODB_CRM_USER" -d "$APP_DB" -c "SELECT 1;"
```
