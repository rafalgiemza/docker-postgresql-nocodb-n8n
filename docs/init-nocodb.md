# Podłączenie NocoDB do appdata (external database)

NocoDB nigdy nie łączy się jako superuser i nie widzi surowych tabel — używa osobnej, ograniczonej roli ograniczonej wyłącznie do schematu `crm` (widoki `v_*`).

**To podłączenie jest teraz w większości zautomatyzowane** przez `scripts/crm-wire-init.sh` (`make wire-apps`, uruchamiane po `make migrate && make seed`) — tworzy source, syncuje tabele, dodaje widoki Kanban/Grid/Calendar. Zostają dwa manualne kroki, bo są jednorazowym bootstrapem konta (patrz "Krok 0" niżej): założenie super-admina i wygenerowanie `NC_API_TOKEN`. Instrukcje poniżej to (a) opis Kroku 0, i (b) ścieżka debugowania/ręcznego odtworzenia, gdy `scripts/crm-wire-init.sh` zawiedzie.

## Krok 0 — jednorazowy bootstrap (ręcznie, raz na hard-reset)

1. Otwórz NocoDB UI → **Sign Up** (pierwsza osoba, która się zaloguje, zostaje super-adminem).
2. Podłącz źródło ręcznie wg kroków 1-2 poniżej — **to jednocześnie test, który rozstrzyga, czy widoki `crm.v_*` (z triggerami INSTEAD OF) w ogóle dają się edytować w gridzie NocoDB**. Zmień dowolną edytowalną kolumnę (np. `next_action` w `v_pipeline`), zapisz, i sprawdź w Postgresie, że zmiana faktycznie doszła do `appdata.opportunities`. Jeśli komórka jest zablokowana/read-only mimo poprawnych grantów — to ograniczenie NocoDB dla widoków z INSTEAD OF, nie coś do naprawienia w schemacie; zgłoś to, zanim ktokolwiek zacznie polegać na automatyzacji widoków.
3. Sprawdź też, jak renderuje się kolumna `stage` w `v_pipeline` — jako Single Select (nadaje się do grupowania w Kanban) czy zwykły tekst. Jeśli tekst, kolumnę trzeba będzie ręcznie przestawić na Single Select z opcjami odpowiadającymi `appdata.opp_stage`, zanim Kanban z `scripts/crm-wire-init.sh` będzie miał sens.
4. Wygeneruj token: ikona konta → **API Tokens** → utwórz → wklej jako `NC_API_TOKEN` w `.env`.

Po tym możesz skasować ręcznie podłączone źródło (albo zostawić — `scripts/crm-wire-init.sh` znajdzie je po nazwie i nie zduplikuje) i uruchomić `make wire-apps`, które odtworzy/dopełni resztę (Kanban, widoki per-osoba, widok notatek) automatycznie.

## 1. Pobranie danych logowania

Na hoście, w katalogu repo:

```bash
grep -E "^(NOCODB_CRM_USER|NOCODB_CRM_PASSWORD|APP_DB)=" .env
```

## 2. Konfiguracja external source w NocoDB

W NocoDB UI → **Create Base** → **Connect to external database** (albo "Create External Source" na istniejącej bazie):

- **Host**: `postgres` (nazwa serwisu w sieci docker-compose)
- **Port**: `5432`
- **Database**: wartość `APP_DB` (domyślnie `appdata`)
- **Schema**: `crm` (**nie** `appdata` ani `public` — to schemat z surowymi tabelami/widokami; NocoDB ma dostęp tylko do `crm.*`)
- **User**: wartość `NOCODB_CRM_USER` (domyślnie `nocodb_crm_user`)
- **Password**: wartość `NOCODB_CRM_PASSWORD`
- **SSL**: wyłączone (ruch wewnątrz sieci docker)

Jeśli NocoDB łączy się spoza sieci compose (inny host / zdalnie), host/port będą inne — do ustalenia osobno.

## 3. Weryfikacja przed podłączeniem w UI

Zanim spróbujesz w UI, zweryfikuj że rola faktycznie się loguje i widzi widoki (eliminuje to zgadywanie, czy problem jest w danych czy w samym NocoDB):

```bash
export $(grep -E '^(NOCODB_CRM_USER|NOCODB_CRM_PASSWORD|APP_DB)=' .env | xargs)
docker exec -e PGPASSWORD="$NOCODB_CRM_PASSWORD" docker-postgres-1 \
  psql -h localhost -U "$NOCODB_CRM_USER" -d "$APP_DB" -c "\dv crm.*"
```

Powinno pokazać 8 widoków: `v_audit_scores`, `v_offer_builder`, `v_offer_goals`, `v_opportunity_dates`, `v_pipeline`, `v_pricing`, `v_tasks`, `v_testimonials`.

## 4. Jeśli "Test Connection" failuje mimo poprawnych danych

Jeśli dostajesz `password authentication failed` (`28P01`) w UI mimo że krok 3 działa poprawnie z tymi samymi danymi — to nie jest problem bazy/sieci/hasła. Zweryfikuj to samo z wnętrza kontenera NocoDB, tym samym klientem `pg`, którego faktycznie używa aplikacja:

```bash
docker exec -w /usr/src/app docker-nocodb-1 node -e "
const { Client } = require('pg');
const c = new Client({ host: 'postgres', port: 5432, user: process.env.NOCODB_CRM_USER, password: process.env.NOCODB_CRM_PASSWORD, database: 'appdata' });
c.connect().then(() => c.query('SELECT 1').then(r => { console.log('OK', r.rows); c.end(); })).catch(e => console.error('FAIL', e.message, e.code));
"
```

Jeśli to działa, a "Test Connection" w UI nadal failuje z identycznymi danymi — problem jest w samym endpoincie/formularzu NocoDB (bug w tej wersji), nie w konfiguracji. Zobacz `docs/hard-reset.md` jako krok do wypróbowania w takiej sytuacji.
