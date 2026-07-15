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
| NocoDB dostęp do danych biznesowych | ✅ gotowe — role rozdzielone (`appdata_owner` / `nocodb_crm_user`), `GRANT ALL PRIVILEGES` usunięty, granty na `crm.*` wgrane | `scripts/init-data.sh`, `.env.example`, `schema.sql` §14 |
| Schemat danych CRM | ✅ gotowe — pełny model wg PRD §2 (rdzeń, audyt, oferty + trigger cenowy, widoki `crm.v_*`, granty) | `schema.sql`, `seed.sql` |
| LibreChat + MongoDB (czat AI dla zespołu) | ✅ gotowe — minimalna instalacja (bez admin-panelu/Meilisearch/RAG API/pgvector z upstream), zero integracji z CRM, wystawione przez Caddy | `docker-compose.yml`, `librechat.yaml`, `.env.example` |
| Segmentacja sieci Docker (`edge`/`internal`/`data`) | ❌ brak — jedna płaska sieć | — |
| PgBouncer | ❌ brak | — |
| MinIO | ✅ gotowe — serwis + `minio-init` (one-shot: buckety `offers`/`templates` (versioning ON), `recordings`/`transcripts`/`backups`, lifecycle 90/30 dni, user `nocodb` scoped tylko do `attachments`), NocoDB podłączony przez `NC_S3_*`, `s3.` domena w Caddy (network alias, żeby jeden `NC_S3_ENDPOINT` działał i z kontenera, i z przeglądarki) | `docker-compose.yml`, `scripts/minio-init.sh`, `Caddyfile`, `.env.example` |
| **crm-api (renderer PPTX/PDF)** | ❌ nie zaczęte — **poza zakresem MVP, patrz §6** | — |
| Uptime Kuma | ✅ gotowe — monitoring/alerting po incydencie 2026-07-14 (post-mortem/tasks.md Task 1), wystawiony przez Caddy na `STATUS_HOST`, monitory/kanały alertów do skonfigurowania ręcznie w UI po pierwszym uruchomieniu | `docker-compose.yml`, `fragments/uptime-kuma.yml`, `Caddyfile`, `.env.example` |
| Job queue / triggery cenowe / historia etapów | ❌ brak | — |

**Wniosek:** infrastruktura bazowa (VPS + n8n + NocoDB + Postgres + Caddy) jest na dobrym poziomie i już realizuje zalecenia z `backups.md`. Naprawa dostępu NocoDB (§2.2) i schemat bazy (§3) są gotowe. Priorytetem MVP jest teraz pipeline n8n/NocoDB (FAZA 3, §4) kończący się na **gotowej, wycenionej ofercie w danych** — bez renderowania pliku.

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

### 2.2 Naprawa dostępu NocoDB → appdata ✅ zrobione
Zrobione — `appdata_owner` (właściciel, migracje/seed) i `nocodb_crm_user` (rola NocoDB, tylko `crm.*`) rozdzielone w `scripts/init-data.sh` + `.env.example`, grant na `crm.*` wgrany w `schema.sql` §14. Analogiczna rola `n8n_crm_user` (scoped na `crm.v_offer_builder`) dodana w `schema.sql` §15 pod FAZĘ 3.

Docelowy kształt (zrealizowany):
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
Zmiana w `.env.example` + `scripts/init-data.sh`: dodać `APPDATA_OWNER_*` i `NOCODB_CRM_USER_*`, usunąć `GRANT ALL PRIVILEGES` dla NocoDB.

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

## 3. Schemat bazy danych — pisany od zera ✅ zrobione

`schema.sql` (930 linii) i `seed.sql` napisane wg PRD §2 od zera i wgrywane przez `scripts/app_migrate.sh`. Zawiera wszystkie sekcje z porządku deklaracji niżej, docelowe widoki `crm.v_*` (§2.7) oraz granty dla `nocodb_crm_user` i `n8n_crm_user`. Reszta tego paragrafu to spec, wg którego plik został napisany — zostawiona jako odniesienie.

**Decyzja (faza testowa, greenfield):** *nie* wdrażamy jeszcze wersjonowanych migracji (dbmate) — ani test, ani prod jeszcze nie istnieją, więc nie ma nic do zachowania między wdrożeniami. Jeden płaski, w pełni re-runnable `schema.sql` (zaczynający się od `DROP SCHEMA IF EXISTS appdata/crm CASCADE`) jest szybszy do iterowania w tej fazie i unika narzutu obsługi migracji, których jeszcze nikt nie musi cofać na żywych danych. Wprowadzenie dbmate wraca jako ostatni krok w FAZIE 6, gdy powstanie pierwsze środowisko z danymi do zachowania (patrz §4, FAZA 6, punkt 6).

Sekcje pliku `schema.sql`, w kolejności deklaracji (tabele w porządku topologicznym względem FK, bez potrzeby migracji między-plikowych): schematy+rozszerzenia → enumy → trigger helper `set_updated_at()` → rdzeń (`users`→`organizations`→`people`→`clients`) → `files` → `pricing_tiers`+`offer_templates` → `opportunities`+historia etapów → `discovery_calls` → audyt (`participants`→`audits`→`audit_scores`→`recommendations`→`recommendation_goals`) → `transcripts`+`extractions` → `offers`+`offer_items` (+ trigger cenowy) → `testimonials`+`offer_snapshots` → `tasks`+`job_queue` → widoki `crm.*` (7 z PRD §2.7 + `v_opportunity_dates` + `v_opportunity_notes`, ta ostatnia z tabelą `opportunity_notes`) → granty dla `nocodb_crm_user`.

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
2. ✅ MinIO + buckety (`offers` versioning ON, `templates` versioning ON, `recordings` lifecycle 90 dni, `transcripts`, `backups` lifecycle 30 dni) — potrzebne już teraz na nagrania/transkrypty i na załączniki/awatary NocoDB, nawet bez renderera. `NC_S3_*` w `nocodb` wskazuje na `MINIO_ENDPOINT` (`https://${MINIO_HOST}`) — ten sam URL musi działać z wewnątrz Dockera (backend NocoDB) i z przeglądarki (presigned download), bo NocoDB zawsze zwraca bezpośrednie, podpisane linki do S3, nie proxuje pobierania przez siebie. Rozwiązane network aliasem na `caddy` (patrz `fragments/caddy.yml`) zamiast dwóch osobnych endpointów. W dev omija się to przez `MINIO_ENDPOINT=http://localhost:9000` w `.env` (MinIO zawsze dostępny na `127.0.0.1:9000`, patrz `fragments/minio.yml`).
3. ✅ Uptime Kuma (monitoring wszystkiego + dysk + cert expiry) — serwis + healthcheck + wystawienie przez Caddy gotowe; monitory/dysk/cert expiry i kanały alertów do skonfigurowania ręcznie w UI (post-mortem/tasks.md Task 1)
4. ✅ Naprawa uprawnień NocoDB (§2.2 wyżej) — zrobione
5. Domena `back-office.coaction.pl` w Caddy (decyzja z PRD §11 — już zaakceptowana przez klienta) — mechanizm gotowy i przetestowany na UAT (`back-office.giemza.dev`), samo `coaction.pl` czeka na DNS od klienta, patrz FAZA 7
6. PgBouncer — **odłożony razem z crm-api** (§6); jego jedyny konsument w PRD to `crm-api`, więc bez sensu wdrażać wcześniej

### FAZA 2 — Baza danych ✅ zrobione
1. ✅ `schema.sql` z §3 wyżej (w Git, wgrywany przez `scripts/app_migrate.sh`)
2. ✅ Seed: `pricing_tiers`, `testimonials`, `users` (dane placeholder, `seed.sql` — realne dane wchodzą w Fazie 6)
3. ✅ Widoki `crm.v_*` + `INSTEAD OF` triggery gdzie trzeba
4. ✅ Grant `nocodb_crm_user` tylko na `crm.*`, `REVOKE CREATE ON SCHEMA appdata/public`
5. ✅ Trigger cenowy i trigger historii etapów działają niezależnie od renderera — to one dają efekt „cena przelicza się na żywo" w demo

### FAZA 3 — n8n + NocoDB (offer builder, bez generowania pliku) 🟡 w trakcie
Pełny runbook: `README.md` §„FAZA 3 — Offer Builder (n8n + NocoDB)".
0. ✅ Fixture danych demo (`seed_demo.sql` + `make seed-demo`) — jedna kompletna oferta (client→opportunity→audit→recommendation→offer, 2 pozycje) do otwarcia w `crm.v_offer_builder`, który wspiera tylko SELECT/UPDATE, nie INSERT. Re-runnable.
1. 🟡 n8n: credential Postgres do `n8n_crm_user` — udokumentowany (host/user/hasło z `.env`), ale **jeszcze nie utworzony w n8n UI** (krok ręczny, poza zasięgiem automatyzacji). Git sync workflowów: potwierdzone z użytkownikiem, że n8n tu jest Community Edition (bez natywnego Source Control) — wersjonowanie robimy ręcznym `n8n export:workflow --all`, udokumentowane w runbooku. Anthropic/NocoDB API credentiale — nadal do zrobienia (FAZA 5 dla Anthropic; NocoDB API tylko jeśli wrócimy do PATCH statusu generowania, poza zakresem MVP).
2. ✅ WF-6 okrojone (`n8n-workflows/wf6-zatwierdz-oferte.json`): Webhook → `UPDATE crm.v_offer_builder SET status='ready' WHERE offer_id=$1` → Respond. Zweryfikowany przez `n8n import:workflow` na lokalnym n8n (2.27.5) — importuje się czysto, żadnych ostrzeżeń o wersjach node'ów. Pozostaje: podpięcie prawdziwego credentiala i aktywacja w UI (placeholder `REPLACE_W_UI` w pliku celowo — sekrety nie idą do Gita).
3. 🟡 NocoDB: widok „Offer Builder" — mapowanie pól na PRD §5 (okrojone, bez `Szablon`/`Status generowania`/`⬇ PPTX`/`⬇ PDF`) udokumentowane w runbooku; budowa samego widoku w NocoDB UI jeszcze nie zrobiona.
4. ✅ Test pętli `60h → 45h` zweryfikowany na poziomie SQL: `UPDATE crm.v_offer_builder SET item1_hours=45, item1_pricing_tier_id=(...)` → `total_price_pln` 20400.00 → 16500.00 PLN natychmiast (trigger PG, bez udziału n8n). Pozostaje powtórzyć klikając w NocoDB UI po zbudowaniu widoku (pkt 3).

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
