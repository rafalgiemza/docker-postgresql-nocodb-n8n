# Plan wdrożenia — stan obecny → MVP (CoAction CRM)

Bazowane na `.ai/PRD.md` (architektura docelowa) i `.ai/backups.md` (poprawki do modelu baz/backupów).
**Środowisko jest nowe** — nie migrowaliśmy starego schematu z `old-sql/` (usunięte z repo po napisaniu `schema.sql` od zera, patrz §7 punkt 5 — historia dostępna w git log). Schemat napisany od zera wg PRD §2.

> **Korekta zakresu MVP:** renderer PPTX/PDF (`crm-api`, FAZA 0 z PRD) jest **wyłączony z MVP** i przesunięty na później (patrz §6). MVP kończy się na w pełni wycenionej, gotowej ofercie **jako dane w NocoDB** (status `ready`, cena przeliczona triggerem, dobrane testimoniale/cele) — bez generowania pliku. To zmienia scenariusz demo w §4.

---

## 1. Co już istnieje w repo (stan faktyczny)

| Element | Stan | Plik |
|---|---|---|
| VPS hardening (ufw, fail2ban, ssh key-only, unattended-upgrades) | ✅ gotowe | `cloud-init.yaml` |
| Docker Compose: postgres, n8n (+runner), nocodb, caddy | ✅ działa | `docker-compose.yml` |
| Rozdział dev/prod | ✅ gotowe — jeden `docker-compose.yml` dla obu (bez override/prod overlay), różnice tylko przez `.env` (hosty/protokół/`LIBRECHAT_URL`); porty dev (postgres/n8n/nocodb/minio/librechat/kuma) zawsze bindowane na `127.0.0.1`, nigdy na sieć | `docker-compose.yml`, `fragments/*.yml`, `.env.example` |
| 3 osobne bazy w jednym Postgresie: `n8n`, `nocodb`, `appdata` | ✅ **już zgodne z `.ai/backups.md`** | `scripts/init-data.sh`, `.env.example` |
| Caddy + TLS dla n8n i nocodb | ✅ gotowe | `Caddyfile` |
| Backup | ✅ gotowe — dumpuje `n8n`/`nocodb`/`appdata` + role (`--roles-only`) + tar attachmentów NocoDB + Mongo do `./backups/`, offsite przez `restic`+`rclone` (dedup, incremental, retencja `--keep-last/--keep-daily/--keep-weekly`); cron na VPS do dodania (patrz setup notes w skrypcie) | `backup/backup.sh`, `backup/mikrus-backup.env.example`, `Makefile` |
| NocoDB dostęp do danych biznesowych | ✅ gotowe — role rozdzielone (`appdata_owner` / `nocodb_crm_user`), `GRANT ALL PRIVILEGES` usunięty; `nocodb_crm_user` ma teraz `CREATE`+`USAGE` na `crm` (nie tylko DML) i domyślny `search_path=crm`, bo NocoDB samo tworzy tabele (patrz §2.2 poniżej) | `scripts/init-data.sh` |
| Schemat danych CRM | ❌ **nie istnieje** — `schema.sql`/`seed.sql`/`seed_demo.sql` (1027/66/150 linii, pełny model wg PRD §2) zgubione w commicie `6cdd64b big refactor` (2026-07-15): inne pliki z `docker/` zostały przeniesione do roota z zachowaniem historii, te trzy po prostu usunięte bez przeniesienia — wygląda na przeoczenie, nie decyzję. Potwierdzone 2026-07-16 na żywym VPS: baza `appdata` miała tylko schemat `public`, `crm` nie istniał wcale. Świadomie **nie odtwarzamy** starego pliku (decyzja 2026-07-16) — patrz §3, nowe podejście |
| LibreChat + MongoDB (czat AI dla zespołu) | ✅ gotowe — minimalna instalacja (bez admin-panelu/Meilisearch/RAG API/pgvector z upstream), zero integracji z CRM, wystawione przez Caddy | `docker-compose.yml`, `librechat.yaml`, `.env.example` |
| Segmentacja sieci Docker (`edge`/`internal`/`data`) | ❌ brak — jedna płaska sieć | — |
| PgBouncer | ❌ brak | — |
| MinIO | ✅ gotowe — serwis + `minio-init` (one-shot: buckety `offers`/`templates` (versioning ON), `recordings`/`transcripts`/`backups`, lifecycle 90/30 dni, user `nocodb` scoped tylko do `attachments`), NocoDB podłączony przez `NC_S3_*`, `s3.` domena w Caddy (network alias, żeby jeden `NC_S3_ENDPOINT` działał i z kontenera, i z przeglądarki) | `docker-compose.yml`, `scripts/minio-init.sh`, `Caddyfile`, `.env.example` |
| **crm-api (renderer PPTX/PDF)** | ❌ nie zaczęte — **poza zakresem MVP, patrz §6** | — |
| Uptime Kuma | ✅ gotowe — monitoring/alerting po incydencie 2026-07-14 (post-mortem/tasks.md Task 1), wystawiony przez Caddy na `STATUS_HOST`, monitory/kanały alertów do skonfigurowania ręcznie w UI po pierwszym uruchomieniu | `docker-compose.yml`, `fragments/uptime-kuma.yml`, `Caddyfile`, `.env.example` |
| Job queue / triggery cenowe / historia etapów | ❌ brak | — |

**Wniosek:** infrastruktura bazowa (VPS + n8n + NocoDB + Postgres + Caddy) jest na dobrym poziomie i już realizuje zalecenia z `backups.md`. Naprawa dostępu NocoDB (§2.2) jest gotowa, ale schemat bazy (§3) trzeba zbudować od zera w NocoDB — `schema.sql` zgubiony w refaktorze 2026-07-15, świadomie nieodtwarzany. Priorytetem jest teraz odbudowa tabel CRM w NocoDB, dopiero potem pipeline n8n/NocoDB (FAZA 3, §4) kończący się na **gotowej, wycenionej ofercie w danych** — bez renderowania pliku.

---

## 2. Decyzje architektoniczne do wdrożenia teraz

### 2.1 Model baz danych (rozstrzyga wątpliwość z `backups.md`)
Zostajemy przy **3 fizycznych bazach** w jednym klastrze Postgresa (już tak jest skonfigurowane) — **nie** dodajemy 4. bazy:

- `n8n` — własność `n8n_user` (już jest, pełne prawa, nietykalne z zewnątrz)
- `nocodb` — meta NocoDB, własność `nocodb_sys_user` (już jest)
- `appdata` — dane biznesowe CRM, **wewnątrz dzielona na dwa schematy**:
  - `appdata.*` — tabele bazowe z PRD §2 (surowe, znormalizowane, z FK/CHECK/triggerami)
  - `crm.*` — wyłącznie widoki `v_*` z PRD §2.7 (`v_pipeline`, `v_offer_builder`, `v_offer_goals`, `v_audit_scores`, `v_tasks`, `v_testimonials`, `v_pricing`) + `v_opportunity_dates`/`v_opportunity_notes` (poza PRD §2.7, patrz schema.sql)

Powód (z `backups.md`): widoki nie mogą odpytywać danych z innej *fizycznej* bazy — muszą żyć w tej samej bazie co tabele źródłowe, stąd podział na schematy, nie na bazy.

### 2.2 Naprawa dostępu NocoDB → appdata ✅ zrobione (zaktualizowane 2026-07-16)
`appdata_owner` (właściciel, migracje/seed — dziś bez realnego użytku, bo nie ma czego migrować, patrz §3) i `nocodb_crm_user` (rola NocoDB) rozdzielone w `scripts/init-data.sh` + `.env.example`.

**Zmiana architektury (2026-07-16):** ponieważ `schema.sql` nie istnieje (§3) i tabele CRM powstają teraz przez klikanie w NocoDB (Creator UI na schemacie `crm`), `nocodb_crm_user` musi mieć `CREATE` — nie tylko DML jak pierwotnie zakładano. Rozdział "kto może zmieniać schemat" pilnuje **rola NocoDB** (Creator vs Editor przy zapraszaniu współpracowników do Base'a), nie grant w Postgresie. `n8n_crm_user` zostaje bez `CREATE` (n8n nigdy nie projektuje schematu) — ale też nie ma dziś żadnych widoków do odpytania (`crm.v_offer_builder` nie istnieje, patrz §3), więc FAZA 3 punkty zależne od tego widoku wymagają ponownej weryfikacji.

Aktualny kształt (`scripts/init-data.sh`, zrealizowany):
```sql
-- właściciel danych appdata — dziś bez realnego zastosowania (nie ma migracji do uruchamiania)
CREATE ROLE appdata_owner WITH LOGIN PASSWORD '...';

-- rola, którą łączy się NocoDB jako external Base — TERAZ z CREATE, bo NocoDB projektuje schemat
CREATE ROLE nocodb_crm_user WITH LOGIN PASSWORD '...';
GRANT CONNECT ON DATABASE appdata TO nocodb_crm_user;
REVOKE CREATE ON SCHEMA public FROM nocodb_crm_user;  -- krytyczne, patrz PRD §8.2 — public nadal zablokowany
CREATE SCHEMA IF NOT EXISTS crm AUTHORIZATION postgres;
GRANT CREATE, USAGE ON SCHEMA crm TO nocodb_crm_user;
ALTER ROLE nocodb_crm_user IN DATABASE appdata SET search_path TO crm;  -- inaczej CREATE TABLE bez prefiksu leci na public i wywala 42501
```

### 2.3 Sieci Docker
Dodać segmentację z PRD §1.2 do `docker-compose.yml`:

| Sieć | Serwisy |
|---|---|
| `edge` | caddy, nocodb, n8n, uptime-kuma |
| `internal` | n8n, crm-api, pgbouncer (jeśli wdrożony), minio |
| `data` | pgbouncer, postgres |

`crm-api` nie ma portu wystawionego przez Caddy — tylko sieć `internal`.

### 2.4 PgBouncer
Wdrażamy zgodnie z PRD §8.1, ale **n8n i NocoDB łączą się bezpośrednio do Postgresa** (port 5432), a **przez PgBouncer idzie tylko `crm-api`** — omija to problem prepared statements w trybie `transaction` bez konieczności podnoszenia `max_prepared_statements`.

### 2.5 LibreChat / MongoDB ✅ zrobione
Dodane wcześniej niż pierwotnie zakładano (klient/Rafał zdecydowali się nie czekać na Fazę 5). Zgodnie z PRD ("osobny byt, zero integracji z CRM w MVP"): własna MongoDB (`docker-compose.yml`), jeden custom endpoint (OpenRouter, reużywa `OPENROUTER_API_KEY`) w `librechat.yaml`, wystawione przez Caddy pod `LIBRECHAT_HOST` — patrz `README.md` sekcja „LibreChat". Celowo bez admin-panelu/Meilisearch/RAG API/pgvector z domyślnego compose upstream — poza budżetem RAM i zakresem PRD. Sieci Dockera nadal płaskie (patrz §2.3 — segmentacja to osobny, jeszcze nie zrobiony punkt), więc `mongo`/`edge` z diagramu PRD §1.2 nie są jeszcze wydzielone.

**Ready-to-migrate (PRD §8.7) ✅:** `MONGO_URI` czytany z `.env`, lokalny kontener `mongodb` pod profilem `local-mongo` (`COMPOSE_PROFILES`). Dokupienie zewnętrznego Mongo = zmiana `MONGO_URI`+`COMPOSE_PROFILES` w `.env` i `make down && make up`, zero edycji compose — patrz `README.md`.

---

## 3. Schemat bazy danych — ❌ porzucony jako plik SQL, tabele powstają w NocoDB (zmiana 2026-07-16)

**Historia:** `schema.sql` (1027 linii), `seed.sql` (66) i `seed_demo.sql` (150) zostały napisane wg PRD §2 i wgrywane przez `scripts/app_migrate.sh` — ale zniknęły z repo w commicie `6cdd64b big refactor` (2026-07-15), najprawdopodobniej przez przeoczenie przy przenoszeniu `docker/*` do roota (inne pliki tego samego refaktoru mają zachowaną historię jako rename, te trzy są czystym usunięciem). Potwierdzone empirycznie 2026-07-16: na żywym VPS baza `appdata` miała tylko schemat `public`, `crm` nie istniał — więc utrata jest realna, nie tylko w plikach repo.

**Decyzja (2026-07-16): świadomie NIE odtwarzamy tego pliku z historii gita.** Zamiast tego: tabele w schemacie `crm` powstają bezpośrednio przez UI NocoDB (Creator rola projektuje strukturę, Editor rola tylko edytuje dane — patrz §2.2). Powód: NocoDB i tak miało być jedynym miejscem pracy z danymi na co dzień, więc odtwarzanie 1027-linijkowego pliku SQL tylko po to, żeby potem tabele tworzyć raz i nie ruszać, nie dawało zwrotu — iteracja przez UI jest szybsza na tym etapie (greenfield, faza testowa, zgodnie z filozofią "nie ma nic do zachowania" poniżej).

**Co to oznacza w praktyce:**
- Brak wersjonowania struktury tabel w gicie — jedynym śladem "jak wygląda schemat" jest stan żywej bazy + `pg_dump` w backupach (patrz `backup/backup.sh`, już to łapie poprawnie).
- Rzeczy, których NocoDB nie wyklika — trigger cenowy (`offer_items` → przelicza `offers.total_hours`/`total_price_pln`, **cena nigdy nie przychodzi z NocoDB/n8n**), trigger historii etapów, widoki `crm.v_*` dla n8n (np. `v_offer_builder`) — nadal wymagają ręcznego SQL, ale **małego, dopisywanego SQL gdy faktycznie potrzebny**, nie jednego dużego pliku z góry. Trzymać go w repo (np. `crm-views-and-triggers.sql`) w miarę powstawania.
- **FAZA 3 poniżej zakłada, że `crm.v_offer_builder` i dane z `seed_demo.sql` już istnieją — to nieaktualne, wymaga ponownej weryfikacji/odbudowy skoro cały `crm` startuje teraz od zera.**
- Import danych z Excela (1600 rekordów, PRD §3, Faza 6) — nadal aktualny jako osobny skrypt Python, ale dopiero gdy docelowe tabele powstaną w NocoDB.

---

## 4. Kolejność wdrożenia (skorygowana pod obecny stan repo, bez renderera)

### FAZA 1 — Domknięcie infrastruktury (rozszerzenie tego, co już jest)
1. Sieci `edge`/`internal`/`data` w `docker-compose.yml`
2. ✅ MinIO + buckety (`offers` versioning ON, `templates` versioning ON, `recordings` lifecycle 90 dni, `transcripts`, `backups` lifecycle 30 dni) — potrzebne już teraz na nagrania/transkrypty i na załączniki/awatary NocoDB, nawet bez renderera. `NC_S3_*` w `nocodb` wskazuje na `MINIO_ENDPOINT` (`https://${MINIO_HOST}`) — ten sam URL musi działać z wewnątrz Dockera (backend NocoDB) i z przeglądarki (presigned download), bo NocoDB zawsze zwraca bezpośrednie, podpisane linki do S3, nie proxuje pobierania przez siebie. Rozwiązane network aliasem na `caddy` (patrz `fragments/caddy.yml`) zamiast dwóch osobnych endpointów. W dev omija się to przez `MINIO_ENDPOINT=http://localhost:9000` w `.env` (MinIO zawsze dostępny na `127.0.0.1:9000`, patrz `fragments/minio.yml`).
3. ✅ Uptime Kuma (monitoring wszystkiego + dysk + cert expiry) — serwis + healthcheck + wystawienie przez Caddy gotowe; monitory/dysk/cert expiry i kanały alertów do skonfigurowania ręcznie w UI (post-mortem/tasks.md Task 1)
4. ✅ Naprawa uprawnień NocoDB (§2.2 wyżej) — zrobione
5. Domena `back-office.coaction.pl` w Caddy (decyzja z PRD §11 — już zaakceptowana przez klienta) — mechanizm gotowy i przetestowany na UAT (`back-office.giemza.dev`), samo `coaction.pl` czeka na DNS od klienta, patrz FAZA 7
6. PgBouncer — **odłożony razem z crm-api** (§6); jego jedyny konsument w PRD to `crm-api`, więc bez sensu wdrażać wcześniej

### FAZA 2 — Baza danych ❌ do zrobienia od zera (schema.sql zgubiony, patrz §3)
1. ❌ Tabele CRM — budowane teraz przez NocoDB Creator UI na schemacie `crm` (nie ma już `schema.sql`/`app_migrate.sh` jako ścieżki wdrożenia)
2. ❌ Seed: `pricing_tiers`, `testimonials`, `users` — `seed.sql`/`seed_demo.sql` zgubione razem ze schematem, dane trzeba wprowadzić ręcznie w NocoDB (albo małym, nowym skryptem, gdy tabele już istnieją)
3. ❌ Widoki `crm.v_*` (w tym `v_offer_builder` potrzebny w FAZIE 3) — nie istnieją, do odtworzenia jako osobny, mały SQL dopiero gdy tabele bazowe będą gotowe w NocoDB
4. ✅ Grant `nocodb_crm_user` — zaktualizowany 2026-07-16: `CREATE`+`USAGE` na `crm` (nie tylko DML), `REVOKE CREATE ON SCHEMA public` — patrz §2.2
5. ❌ Trigger cenowy i trigger historii etapów — nie istnieją, do napisania jako SQL gdy tabele `offers`/`offer_items`/`opportunities` powstaną w NocoDB

### FAZA 3 — n8n + NocoDB (offer builder, bez generowania pliku) 🟡 w trakcie — ⚠️ punkty 0/2/4 do re-weryfikacji, patrz §3
Pełny runbook: `README.md` §„FAZA 3 — Offer Builder (n8n + NocoDB)". **Uwaga (2026-07-16):** poniższe ✅ zakładają, że `crm.v_offer_builder` i dane z `seed_demo.sql` istnieją — od czasu utraty `schema.sql` (§3) to nieprawda na żywym VPS (potwierdzone: `appdata` miał tylko `public`). Status trzeba sprawdzić ponownie i odtworzyć po zbudowaniu tabel w NocoDB.
0. ⚠️ (było ✅) Fixture danych demo (`seed_demo.sql` + `make seed-demo`) — jedna kompletna oferta (client→opportunity→audit→recommendation→offer, 2 pozycje) do otwarcia w `crm.v_offer_builder`. Plik zgubiony razem ze schematem — do odtworzenia po zbudowaniu tabel bazowych w NocoDB.
1. 🟡 n8n: credential Postgres do `n8n_crm_user` — udokumentowany (host/user/hasło z `.env`), ale **jeszcze nie utworzony w n8n UI** (krok ręczny, poza zasięgiem automatyzacji). Git sync workflowów: potwierdzone z użytkownikiem, że n8n tu jest Community Edition (bez natywnego Source Control) — wersjonowanie robimy ręcznym `n8n export:workflow --all`, udokumentowane w runbooku. Anthropic/NocoDB API credentiale — nadal do zrobienia (FAZA 5 dla Anthropic; NocoDB API tylko jeśli wrócimy do PATCH statusu generowania, poza zakresem MVP).
2. ⚠️ (było ✅) WF-6 okrojone (`n8n-workflows/wf6-zatwierdz-oferte.json`): Webhook → `UPDATE crm.v_offer_builder SET status='ready' WHERE offer_id=$1` → Respond. Workflow JSON sam w sobie jest OK (zweryfikowany przez `n8n import:workflow`), ale odwołuje się do widoku `crm.v_offer_builder`, który dziś nie istnieje — nie zadziała, dopóki widok nie zostanie odtworzony.
3. 🟡 NocoDB: widok „Offer Builder" — mapowanie pól na PRD §5 (okrojone, bez `Szablon`/`Status generowania`/`⬇ PPTX`/`⬇ PDF`) udokumentowane w runbooku; budowa samego widoku w NocoDB UI jeszcze nie zrobiona. Teraz zależy też od tego, czy tabele bazowe (`opportunities`, `offers`, `offer_items`...) w ogóle istnieją w `crm` — dziś nie istnieją.
4. ⚠️ (było ✅) Test pętli `60h → 45h` — zależał od triggera cenowego ze zgubionego `schema.sql`; do odtworzenia (trigger + tabele) i przetestowania od nowa po zbudowaniu struktury w NocoDB.

### FAZA 4 — DEMO 🎯 (bez pliku wyjściowego)
Przemek otwiera rekord, zmienia `60h → 45h`, widzi przeliczoną cenę, zmienia testimoniale, klika „Zatwierdź ofertę" → status `ready`. Payoff demo to **żywa wycena i dobór treści**, nie plik PPTX.

### FAZA 5 — Reszta pipeline'u
WF-1…WF-5, WF-7 (bez inspekcji szablonu — nieaktualne bez renderera), WF-8, Cal.com webhook, AI-ekstrakcja (Anthropic), migracja danych z Excela (1600 rekordów, skrypt jednorazowy, patrz §3).

### FAZA 6 — Backup, hardening, przekazanie
1. ✅ **`backup/backup.sh`** (wywoływany przez `make backup`) — dumpuje role (`--roles-only`), `n8n`, `nocodb`, `appdata` oraz tar attachmentów NocoDB i mongodump LibreChat, wszystko pod wspólnym `$TS` do `./backups/`. (Format plain SQL, nie `-Fc`, na razie wystarczający.)
2. ✅ Offsite: `restic` (dedup, incremental, retencja `--keep-last/--keep-daily/--keep-weekly`) + `rclone` (R2/B2) — patrz setup notes w `backup/backup.sh` i `backup/mikrus-backup.env.example`. Pozostaje do zrobienia na VPS: `rclone config`, `restic init`, i dodanie cron entries z tych setup notes (`make backup` co 30 min, `make backup-prune` raz dziennie).
3. Zabezpieczyć `N8N_ENCRYPTION_KEY` w password managerze klienta — bez niego dump `n8n` DB jest bezużyteczny
4. **Restore drill na czystym VPS — obowiązkowy przed oddaniem** (dumpy + role + `.env` + MinIO)
5. Runbook (restart, restore, dodanie pola) + szkolenie klienta
6. **Wprowadzenie wersjonowanych migracji (dbmate)** — przejście z płaskiego `schema.sql` na `migrations/*.sql` w dbmate, dopiero gdy powstanie pierwsze środowisko z danymi do zachowania między wdrożeniami (dziś: faza testowa, greenfield, nic do ochrony). Ostatni krok całego wdrożenia — po tym punkcie schemat przestaje być "jednym plikiem wgrywanym hurtem" i staje się właściwie wersjonowany, z historią `schema_migrations` i bezpiecznymi rollbackami.

### FAZA 7 — Prod: wystawienie n8n/NocoDB pod domenami klienta 🟡 UAT zrobione, prod czeka na klienta
1. ✅ Model sieciowy: VPS (Mikrus) ma własny dedykowany adres IPv6 (`2a01:4f9:3a:3f89::268`), Cloudflare AAAA (proxied, ☁️) kieruje na niego bezpośrednio — Caddy sam robi automatic HTTPS (Let's Encrypt) na 80/443, routing po Host header, zgodnie z tym, co już jest w `Caddyfile`/`fragments/caddy.yml`. `ufw` ma otwarte 80/443 na IPv4 i IPv6.
2. ❌ Odrzucone: mikr.us `domena` (współdzielony port na edge'u mikr.us) — przetestowane i wycofane, bo `domena` proxuje na warstwie HTTP (nie robi SNI/TCP passthrough), co łamie automatic HTTPS Caddy'ego (błędy 521, pętle przekierowań). Nie używać do tego serwisu.
3. ✅ UAT zrobiony na domenie Rafała: `n8n.giemza.dev` + `back-office.giemza.dev`, certy Let's Encrypt (prod CA, nie staging) wydane poprawnie, oba serwisy działają end-to-end przez Cloudflare.
4. 🟡 Prod (`coaction.pl`) — czeka na akceptację klienta. Po akceptacji: klient dodaje analogiczne rekordy AAAA (`n8n.coaction.pl`, `back-office.coaction.pl` → ten sam adres IPv6 VPS-a), Rafał podmienia `N8N_HOST`/`NC_HOST`/`WEBHOOK_URL` w `.env` z `giemza.dev` na `coaction.pl` i robi `make down && make up`. Zero zmian w kodzie poza `.env`.

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
2. Kto dostaje taski — częściowo potwierdzone (rozmowa z klientem 2026-07-12, patrz `seed.sql`): Przemek (sales), Dorota (auditor, B2B), Ola/Aleksandra (auditor, B2C) zasiane jako `appdata.users`. Wciąż otwarte: role Kasi (Growth Manager) i Pauliny (opiekunka finansowa) — nie zamodelowane w `appdata.users.role` CHECK (brak `finance`/`marketing`).
3. Offsite backup — Backblaze B2 czy Hetzner Storage Box?
4. Dostawca ASR — Deepgram / AssemblyAI / OpenAI Whisper API?

Nowe, z przeglądu repo i korekty zakresu:
5. ✅ `old-sql/*.sql` usunięte z repo (refaktor struktury, patrz TEMPLATE/coaction/.ai/about.md) — historia dostępna w git log, nie jako pliki w drzewie.
6. dbmate czy inne narzędzie migracji — akceptacja wyboru? (odłożone do FAZY 6, nieblokujące dla MVP — patrz §3 i §4)
7. **Jak MVP „zamyka" ofertę bez pliku** — status `ready` w NocoDB wystarczy jako koniec MVP, czy potrzebny jest jakiś ręczny eksport/kopiowanie danych do istniejącego szablonu jako tymczasowy obejście do czasu renderera?
