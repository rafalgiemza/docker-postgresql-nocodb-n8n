# Plan wdrożenia — stan obecny → MVP (CoAction CRM)

Bazowane na `.ai/PRD.md` (architektura docelowa) i `.ai/backups.md` (poprawki do modelu baz/backupów).
**Środowisko jest nowe** — nie migrujemy starego schematu z `old-sql/`. Piszemy schemat od zera wg PRD §2.
Stare pliki `old-sql/schema.sql`, `old-sql/schema1_big.sql`, `old-sql/seed.sql` traktujemy jako **wyłącznie referencję** (są to wcześniejsze, uproszczone szkice tego samego pomysłu) — nie jako punkt startowy migracji.

> **Korekta zakresu MVP:** renderer PPTX/PDF (`crm-api`, FAZA 0 z PRD) jest **wyłączony z MVP** i przesunięty na później (patrz §6). MVP kończy się na w pełni wycenionej, gotowej ofercie **jako dane w NocoDB** (status `ready`, cena przeliczona triggerem, dobrane testimoniale/cele) — bez generowania pliku. To zmienia scenariusz demo w §4.

---

## 1. Co już istnieje w repo (stan faktyczny)

| Element | Stan | Plik |
|---|---|---|
| VPS hardening (ufw, fail2ban, ssh key-only, unattended-upgrades) | ✅ gotowe | `docker/cloud-init.yaml` |
| Docker Compose: postgres, n8n (+runner), nocodb, caddy | ✅ działa | `docker/docker-compose.yml` |
| Rozdział dev/prod (`override.yml` / `prod.yml`) | ✅ gotowe | `docker/docker-compose.*.yml` |
| 3 osobne bazy w jednym Postgresie: `n8n`, `nocodb`, `appdata` | ✅ **już zgodne z `.ai/backups.md`** | `docker/init-data.sh`, `docker/.env.example` |
| Caddy + TLS dla n8n i nocodb | ✅ gotowe | `docker/Caddyfile` |
| Backup | ✅ gotowe (lokalnie) — dumpuje `n8n`/`nocodb`/`appdata` + role (`--roles-only`) + tar attachmentów NocoDB; offsite transfer robiony ręcznie, cron do dodania później | `docker/Makefile` |
| NocoDB dostęp do danych biznesowych | 🟡 role rozdzielone (`appdata_owner` / `nocodb_crm_user`), `GRANT ALL PRIVILEGES` usunięty; grant na `crm.*` czeka na migrację `0010_grants_nocodb_crm_user.sql` (§3), bo schemat jeszcze nie istnieje | `docker/init-data.sh`, `docker/.env.example` |
| Schemat danych CRM | ❌ wczesny szkic (`clients/deals/offers…`), nie model docelowy z PRD §2 | `old-sql/*.sql` (referencja, nie do wgrania) |
| Segmentacja sieci Docker (`edge`/`internal`/`data`) | ❌ brak — jedna płaska sieć | — |
| PgBouncer | ❌ brak | — |
| MinIO | ❌ brak | — |
| **crm-api (renderer PPTX/PDF)** | ❌ nie zaczęte — **poza zakresem MVP, patrz §6** | — |
| Uptime Kuma | ❌ brak | — |
| Job queue / triggery cenowe / historia etapów | ❌ brak | — |

**Wniosek:** infrastruktura bazowa (VPS + n8n + NocoDB + Postgres + Caddy) jest na dobrym poziomie i częściowo już realizuje zalecenia z `backups.md`. Priorytetem MVP jest teraz: naprawa dostępu NocoDB (§2.2), schemat bazy (§3) i pipeline n8n/NocoDB kończący się na **gotowej, wycenionej ofercie w danych** — bez renderowania pliku.

---

## 2. Decyzje architektoniczne do wdrożenia teraz

### 2.1 Model baz danych (rozstrzyga wątpliwość z `backups.md`)
Zostajemy przy **3 fizycznych bazach** w jednym klastrze Postgresa (już tak jest skonfigurowane) — **nie** dodajemy 4. bazy:

- `n8n` — własność `n8n_user` (już jest, pełne prawa, nietykalne z zewnątrz)
- `nocodb` — meta NocoDB, własność `nocodb_sys_user` (już jest)
- `appdata` — dane biznesowe CRM, **wewnątrz dzielona na dwa schematy**:
  - `appdata.*` — tabele bazowe z PRD §2 (surowe, znormalizowane, z FK/CHECK/triggerami)
  - `crm.*` — wyłącznie widoki `v_*` z PRD §2.7 (`v_pipeline`, `v_offer_builder`, `v_offer_goals`, `v_audit_scores`, `v_tasks`, `v_testimonials`, `v_pricing`)

Powód (z `backups.md`): widoki nie mogą odpytywać danych z innej *fizycznej* bazy — muszą żyć w tej samej bazie co tabele źródłowe, stąd podział na schematy, nie na bazy.

### 2.2 Naprawa dostępu NocoDB → appdata ⚠️ priorytet
Dziś `APP_DB_USER` jest **właścicielem** całej bazy `appdata` (`GRANT ALL PRIVILEGES`) i tym userem łączy się NocoDB. To jest dokładnie sytuacja, przed którą ostrzega `backups.md` — NocoDB może teoretycznie zmienić strukturę tabel bazowych.

Docelowo:
```sql
-- właściciel danych (migracje, seed) — NIE używany przez NocoDB
CREATE ROLE appdata_owner WITH LOGIN PASSWORD '...';

-- rola, którą łączy się NocoDB jako external Base
CREATE ROLE nocodb_crm_user WITH LOGIN PASSWORD '...';
GRANT CONNECT ON DATABASE appdata TO nocodb_crm_user;
GRANT USAGE ON SCHEMA crm TO nocodb_crm_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA crm TO nocodb_crm_user;
REVOKE ALL ON SCHEMA appdata FROM nocodb_crm_user;
REVOKE CREATE ON SCHEMA public FROM nocodb_crm_user;  -- krytyczne, patrz PRD §8.2
```
Zmiana w `docker/.env.example` + `docker/init-data.sh`: dodać `APPDATA_OWNER_*` i `NOCODB_CRM_USER_*`, usunąć `GRANT ALL PRIVILEGES` dla NocoDB.

### 2.3 Sieci Docker
Dodać segmentację z PRD §1.2 do `docker/docker-compose.yml`:

| Sieć | Serwisy |
|---|---|
| `edge` | caddy, nocodb, n8n, uptime-kuma |
| `internal` | n8n, crm-api, pgbouncer (jeśli wdrożony), minio |
| `data` | pgbouncer, postgres |

`crm-api` nie ma portu wystawionego przez Caddy — tylko sieć `internal`.

### 2.4 PgBouncer
Wdrażamy zgodnie z PRD §8.1, ale **n8n i NocoDB łączą się bezpośrednio do Postgresa** (port 5432), a **przez PgBouncer idzie tylko `crm-api`** — omija to problem prepared statements w trybie `transaction` bez konieczności podnoszenia `max_prepared_statements`.

### 2.5 LibreChat / MongoDB
**Poza zakresem tej fazy.** PRD sam to oznacza jako "osobny byt, zero integracji z CRM w MVP". Dodajemy dopiero po demo (Faza 5), jeśli klient tego chce — zero wpływu na CRM pipeline.

---

## 3. Schemat bazy danych — pisany od zera

Zamiast migrować `old-sql/`, tworzymy nowy katalog migracji wg PRD §2, w jednej logicznej kolejności:

```
docker/migrations/
  0001_enums.sql
  0002_core_organizations_people_clients.sql
  0003_opportunities_and_stage_history.sql       -- + trigger historii etapów
  0004_discovery_transcripts_extractions.sql      -- pg_trgm, tsvector 'simple'
  0005_audits_scores_recommendations.sql
  0006_pricing_offers_offer_items.sql             -- + trigger cenowy
  0007_testimonials_offer_templates_snapshots.sql
  0008_tasks_job_queue_files.sql
  0009_views_crm_schema.sql                       -- v_pipeline, v_offer_builder, ...
  0010_grants_nocodb_crm_user.sql                 -- REVOKE CREATE, grant tylko na crm.*
  0011_seed_pricing_tiers_testimonials_users.sql
```

Rekomendacja narzędzia: **dbmate** (pojedynczy binarz, czyste SQL migracje, pasuje do istniejącego stylu `app_migrate.sh`) zamiast jednego dużego `schema.sql` wykonywanego za każdym razem. Zastępuje to obecny `docker/app_migrate.sh` (dziś: jeden plik `schema.sql` wgrywany hurtem, bez wersjonowania).

Kluczowe elementy nie do pominięcia (z PRD, ryzykowne miejsca):
- `search_tsv` z `to_tsvector('simple', ...)` — **nie `'polish'`**, transkrypty są dwujęzyczne
- trigger cenowy `BEFORE/AFTER` na `offer_items` → przelicza `offers.total_hours`/`total_price_pln`; **cena nigdy nie przychodzi z NocoDB/n8n**
- trigger `AFTER UPDATE OF stage ON opportunities` → zapis do `opportunity_stage_history`
- `job_queue` z `FOR UPDATE SKIP LOCKED` zamiast Redis/Celery

Dane referencyjne do zasiania (`0011_seed_...`): cennik ze slajdu 8 (PRD §2.5), katalog testimoniali (slajdy 12–24), lista userów (Przemek, Ola/Dorota jako auditorzy).

> Migracja **danych biznesowych** z Excela (1600 rekordów, PRD §3) to osobny, jednorazowy skrypt Python (`openpyxl`+`psycopg`) uruchamiany **po** wdrożeniu schematu na docelowym środowisku — to nie jest migracja schematu, tylko import danych, i zostaje w planie jako Faza 6.

---

## 4. Kolejność wdrożenia (skorygowana pod obecny stan repo, bez renderera)

### FAZA 1 — Domknięcie infrastruktury (rozszerzenie tego, co już jest)
1. Sieci `edge`/`internal`/`data` w `docker-compose.yml`
2. MinIO + buckety (`offers` versioning ON, `templates` versioning ON, `recordings` lifecycle 90 dni, `transcripts`, `backups` lifecycle 30 dni) — potrzebne już teraz na nagrania/transkrypty, nawet bez renderera
3. Uptime Kuma (monitoring wszystkiego + dysk + cert expiry)
4. Naprawa uprawnień NocoDB (§2.2 wyżej)
5. Domena `back-office.coaction.pl` w Caddy (decyzja z PRD §11 — już zaakceptowana przez klienta)
6. PgBouncer — **odłożony razem z crm-api** (§6); jego jedyny konsument w PRD to `crm-api`, więc bez sensu wdrażać wcześniej

### FAZA 2 — Baza danych
1. Migracje z §3 wyżej (dbmate, w Git)
2. Seed: `pricing_tiers`, `testimonials`, `users`
3. Widoki `crm.v_*` + `INSTEAD OF` triggery gdzie trzeba
4. Grant `nocodb_crm_user` tylko na `crm.*`, `REVOKE CREATE ON SCHEMA appdata/public`
5. Trigger cenowy i trigger historii etapów działają niezależnie od renderera — to one dają efekt „cena przelicza się na żywo" w demo

### FAZA 3 — n8n + NocoDB (offer builder, bez generowania pliku)
1. n8n: credentials (PG bezpośrednio, Anthropic, NocoDB API), Git sync workflowów
2. WF-6 okrojone: **„Zatwierdź ofertę"** zamiast „Generuj ofertę" — ustawia `offers.status='ready'`, bez wywołania `crm-api` (którego jeszcze nie ma)
3. NocoDB: widok „Offer Builder" wg PRD §5, pola nazwane jak slajdy (pola `⬇ PPTX`/`⬇ PDF` i `Status generowania` chwilowo ukryte/nieużywane)
4. Test pętli: `60h → 45h` → cena przelicza się (trigger PG) na żywo w NocoDB

### FAZA 4 — DEMO 🎯 (bez pliku wyjściowego)
Przemek otwiera rekord, zmienia `60h → 45h`, widzi przeliczoną cenę, zmienia testimoniale, klika „Zatwierdź ofertę" → status `ready`. Payoff demo to **żywa wycena i dobór treści**, nie plik PPTX.

### FAZA 5 — Reszta pipeline'u
WF-1…WF-5, WF-7 (bez inspekcji szablonu — nieaktualne bez renderera), WF-8, Cal.com webhook, AI-ekstrakcja (Anthropic), migracja danych z Excela (1600 rekordów, skrypt jednorazowy, patrz §3).

### FAZA 6 — Backup, hardening, przekazanie
1. ✅ **`docker/Makefile` `backup`** rozszerzony — dumpuje role (`--roles-only`), `n8n`, `nocodb`, `appdata` oraz tar attachmentów NocoDB, wszystko pod wspólnym `$(TS)`. (Format plain SQL, nie `-Fc`, na razie wystarczający.)
2. Offsite: transfer robiony ręcznie przez klienta/Rafała; cron do dodania później. Docelowo MinIO `mc mirror` → Backblaze B2 / Hetzner Storage Box (PRD §11, do potwierdzenia z klientem)
3. Zabezpieczyć `N8N_ENCRYPTION_KEY` w password managerze klienta — bez niego dump `n8n` DB jest bezużyteczny
4. **Restore drill na czystym VPS — obowiązkowy przed oddaniem** (dumpy + role + `.env` + MinIO)
5. Runbook (restart, restore, dodanie pola) + szkolenie klienta

---

## 6. Poza zakresem MVP — renderer PPTX/PDF (do zrobienia później)

Przesunięte z pierwotnej FAZY 0/3. Kiedy przyjdzie kolej (po demo, gdy klient potwierdzi kierunek):

1. **Bramka techniczna** (to, co PRD nazywało FAZA 0 — test ryzyka technicznego):
   - Szablon z decku 1638 → `.potx`, placeholdery na slajdach 1, 3, 4, 5–7
   - Minimalny `render_offer.py` (hardcoded JSON → PPTX) — merge runów per paragraf przed podmianą tekstu
   - Test klonowania/usuwania slajdów celów (`python-pptx` bez API do kopiowania — `copy.deepcopy` XML); Plan B: 3 gotowe slajdy, tylko usuwanie
   - Test `soffice --headless --convert-to pdf`, unikalny `-env:UserInstallation`, timeout 60s
2. **crm-api jako serwis:** FastAPI + Pydantic v2 + `python-pptx` + LibreOffice, `POST /render`, `POST /template/inspect`, `GET /health`, integracja z MinIO (cache po `sha256`), sieć `internal` bez portu w Caddy
3. **PgBouncer** — dopiero wtedy ma konsumenta
4. Podłączenie z powrotem do WF-6 (przywrócenie „Generuj ofertę" jako pełnego kroku z plikiem) i WF-7 (upload/inspekcja szablonu)
5. Pola `⬇ PPTX`/`⬇ PDF`/`Status generowania` wracają do widoku Offer Builder w NocoDB
6. `cpu_shares` (postgres 2048, crm-api 512, patrz PRD §7) — ma sens dopiero gdy `crm-api` faktycznie zużywa CPU

**Powód przesunięcia:** to jedyny prawdziwy risk techniczny projektu (PRD sam to podkreśla), ale nie blokuje reszty pipeline'u — dane, wycena i workflow mogą działać i być demonstrowane bez generowania pliku. Odizolowanie go pozwala dowieźć resztę MVP bez czekania na rozstrzygnięcie tego ryzyka.

---

## 7. Otwarte pytania (do potwierdzenia)

Z PRD §11, wciąż aktualne:
1. Czy Przemek akceptuje brak ręcznej edycji PPTX (docelowo, gdy renderer wróci w zakres)?
2. Kto dostaje taski — lista: Przemek / Ola / Dorota / Kasia / Paulina?
3. Offsite backup — Backblaze B2 czy Hetzner Storage Box?
4. Dostawca ASR — Deepgram / AssemblyAI / OpenAI Whisper API?

Nowe, z przeglądu repo i korekty zakresu:
5. Czy `old-sql/*.sql` można usunąć z repo po napisaniu nowego schematu, czy zostawić jako archiwum referencyjne?
6. dbmate czy inne narzędzie migracji — akceptacja wyboru?
7. **Jak MVP „zamyka" ofertę bez pliku** — status `ready` w NocoDB wystarczy jako koniec MVP, czy potrzebny jest jakiś ręczny eksport/kopiowanie danych do istniejącego szablonu jako tymczasowy obejście do czasu renderera?
