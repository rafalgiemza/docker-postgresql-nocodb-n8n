# PRD — CoAction CRM (NocoDB + n8n + PostgreSQL)

Wersja: 2.0 · Data: 2026-07-18 · Status: faza 1 w trakcie wdrożenia

> **Historia wersji:** Wersja 1.x tego dokumentu (do 12.07) opisywała inną architekturę —
> znormalizowany schemat Postgresa (`organizations/people/clients/opportunities/offers/
> offer_items` + trigger cenowy) z NocoDB ograniczonym do widoków `crm.v_*` i osobnym
> serwisem `crm-api` generującym oferty jako PPTX/PDF. Ten kierunek został **porzucony
> 2026-07-17/18** na rzecz prostszego modelu, w którym NocoDB samo zarządza tabelami
> (przez Creator UI, bezpośrednio na Postgresie) — patrz §5 i §11. Stary schemat
> (`appdata/appdata_schema.sql`) i stare workflowy (`n8n-workflows/wf1-wf6*.json`)
> zostają w repo jako materiał historyczny, ale są nieużywane i nie opisują dzisiejszego
> stanu. Kontrakt `crm-api`/renderer PPTX z tamtej wersji jest zachowany jako gotowy
> projekt w backlogu (§12), na wypadek gdyby generowanie plików wróciło do zakresu —
> patrz otwarte pytanie w §14.

## 1. Kontekst i cel

CoAction (szkoła językowa B2B/B2C, ~5-osobowy zespół) zastępuje Asanę (za droga)
i Excela CEO (CRM w arkuszu, 35 kolumn, zdenormalizowany) jednym self-hosted
systemem: **NocoDB** (baza + widoki + formularze) + **n8n** (automatyzacje)
+ **PostgreSQL** (źródło prawdy, raporty SQL). Cel biznesowy: jedna baza danych
o leadach, spotkaniach i taskach; automatyzacja powtarzalnej pracy krok po
kroku, zaczynając od miejsc, gdzie dane wpadają ręcznie.

**Kryteria sukcesu fazy 1:** zespół pracuje wyłącznie w NocoDB (twarde cięcie
z Asaną/Excelem, historia zaimportowana), każdy widzi swoje taski i kalendarz,
lead ma czytelny timeline, nikt nie przepisuje danych między systemami.

## 2. Użytkownicy i role

| Osoba | Rola | Główne widoki |
|---|---|---|
| Przemek (CEO) | handlowiec, owner leadów, weryfikacja AI i dopasowań | kanban leads, taski, kolejka weryfikacji |
| Dorota | metodyczka B2B — cele szkoleniowe, audyty firmowe | taski, meetings (audyty), participants |
| Aleksandra | metodyczka B2C/1:1 — cele, audyty indywidualne | jw. |
| Paulina | finanse | taski cykliczne (fakturowanie) |
| Kasia | marketing | taski, projekty marketingowe |
| analityk (rola) | dobór referencji do ofert | taski, testimonials |

## 3. Zakres

**Faza 1 (ten dokument):** model danych, widoki, workflowy W1–W6b, intake
z 3 źródeł z kaskadą dopasowań, import legacy, Test Runner, lustro xlsx dla CEO
(okres przejściowy).

**Poza zakresem fazy 1 (ustalone):** tabela `offers`, formularze przed-audytowe,
dashboardy SQL, wyszukiwanie po zamkniętej historii.

**Otwarte, nierozstrzygnięte:** generowanie oferty jako pliku (PPTX/www) — poprzednia
wersja PRD traktowała to jako rdzeń MVP, aktualna robocza linia zakłada, że oferta
kończy się jako gotowe, wycenione dane w NocoDB (status `draft_ready`), ale to nie
zostało formalnie potwierdzone z klientem/CEO. Patrz §14.

## 4. Infrastruktura

**Hosting: 2× Sfera Host VPS PRO** (KVM, 4 współdzielone vCPU, 12 GB RAM, 120 GB NVMe,
1 IPv4 + darmowe IPv6, Polska, 59 PLN netto/mies. każdy) — **stan bieżący**, oba
serwery wykupione i działają, pełny stack na obu, 100% uptime na obu od uruchomienia.
Zastąpiły Mikr.us 4.1 (powtarzające się stalle dysku I/O, `post-mortem/logs.md`,
`post-mortem/vps-migration-decision.md`) — decyzja klienta zaakceptowana 2026-07-17.

- **VPS-A = produkcja**, **VPS-B = staging/test** (target Test Runnera).
  Identyczny compose na obu; na VPS-B `WH_PREFIX=""` — osobny n8n eliminuje
  potrzebę kopii workflowów `-TEST` i prefiksów ścieżek (wystarczy sed z ID
  tabel bazy testowej tamtej instancji).
- **Znane ograniczenie CPU (rozwiązane):** przy pierwszym deployu na Sferahost oba
  VPS-y pokazywały domyślny, konserwatywny model CPU QEMU (`QEMU Virtual CPU version
  2.5+`, flagi kończące się na SSE2 — brak AVX/x86-64-v2), co wywalało `mongodb`
  (wymaga AVX od wersji 5+) i `minio` (wymaga x86-64-v2). To była konfiguracja hosta
  (brak `host-passthrough`), nie realny limit fizycznego CPU — zgłoszone i naprawione
  przez Sferahost. Do potwierdzenia: czy `host-passthrough` przetrwa ewentualną
  migrację VM między hostami klastra dostawcy.
- **MinIO OSS jest martwe od 2026-04**: upstream (`minio/minio`) oznaczony jako
  nieutrzymywany, zarchiwizowany na stałe; firma przeszła na płatny AIStor.
  `RELEASE.2025-10-15T17-29-55Z` to ostatni release, jaki kiedykolwiek powstanie —
  wersja jest jawnie przypięta w `.env.example`. Decyzja "zamrożone na stałe vs.
  migracja na Garage/SeaweedFS" nie jest podjęta — istotne, jeśli w przyszłości
  powstanie integracja S3 SDK (np. renderer ofert, patrz §12).
- Stack (docker compose, `include:` z `fragments/*.yml`): `postgres`, `nocodb`,
  `n8n` + `n8n-runner`, `minio` + `minio-init`, `mongodb` (tylko dla LibreChat),
  `librechat`, `uptime-kuma`, `beszel` + `beszel-agent`, `budibase` (low-code
  internal-tools builder, dodany 2026-07-18 — własny CouchDB+Redis, ale reużywa
  wspólne MinIO na storage), `autoheal`, `caddy` (80/443, TLS) — kontenery
  aplikacyjne bez publikowanych portów, ruch tylko przez Caddy.
- Ruch wewnętrzny po nazwach serwisów: n8n→NocoDB `http://nocodb:8080`,
  NocoDB→n8n `http://n8n:5678/webhook/...` (nie przez publiczny internet).
- Postgres: jedna instancja, bazy `n8n`/`nocodb`/`appdata` (rola `n8n`/`nocodb`
  własne, `appdata` dzielona na schemat `crm` — tabele tworzone bezpośrednio przez
  NocoDB Creator UI, patrz §5) + `rag_db` (przygotowanie pod RAG, poza zakresem
  fazy 1, patrz README.md).
- **Backup (wymaganie twarde):** `make backup` (`backup/backup.sh`) dumpuje role +
  `n8n`/`nocodb`/`appdata` + attachmenty NocoDB + mongodump LibreChat do
  `./backups/`, offsite przez `restic`+`rclone` (dedup, incremental, retencja
  `--keep-last/--keep-daily/--keep-weekly`). **Cron na VPS-ach i realny offsite
  target (Backblaze B2 / Hetzner Storage Box) wciąż do dopięcia — priorytet #1**,
  patrz §13 i §14.
- MailHog na VPS-B jako SMTP-atrapa dla testów (UI :8025 wewn.).

Pełna tabela usług + dostęp: `README.md`.

## 5. Model danych (baza NocoDB, 9 tabel)

Szczegóły: `fable/nocodb_crm_schema_v2.md`. Skrót relacji:

```
companies ──< leads ──< meetings / participants / tasks / activities
    │           └── }o--o{ testimonials
    └─────< participants ── |o--o{ meetings (audyt per osoba)
projects ──< tasks >── task_templates
```

> Ten model **zastępuje** wcześniejszy znormalizowany schemat Postgresa
> (`organizations/people/clients/opportunities/offers/offer_items`, trigger
> cenowy — patrz historia wersji na górze dokumentu). Tabele nie powstają już z
> pliku migracji SQL — są tworzone bezpośrednio przez NocoDB Creator UI na
> Postgresie (rola `nocodb_crm_user` z `CREATE`+`USAGE` na schemacie `crm`,
> `REVOKE CREATE ON SCHEMA public` pozostaje krytyczne). Jedynym śladem "jak
> wygląda schemat" jest stan żywej bazy + `pg_dump` w backupach; mały, ręcznie
> pisany SQL (widoki, triggery) dopisywany tylko gdy faktycznie potrzebny.
> Baza testowa "CoAction TEST Base" już istnieje (`fable/meta.json`, utworzona
> 2026-07-17) i implementuje dokładnie ten model.

- `leads` — szansa sprzedaży; kanban po `stage`, `state` (open/won/lost/archived),
  pipeline oferty `offer_prep_status`, statusy dopasowań `company_match_status`
  i `duplicate_check` + self-link `possible_duplicate`, licznik `enquiry_no`,
  kamienie milowe pisane przez n8n (`received_at`, `offer_sent_at`,
  `contract_sent_at`, `closed_at`), `legacy_id` (import).
- `companies` — byt trwały, `domains` jako klucz dedupu.
- `participants` — osoby szkolone (≠ kupujący); 5 ocen CEFR ze slajdów ofert.
- `meetings` — tylko realne spotkania; `transcript`, `ai_analysis` (n8n),
  maszyna stanów `processing_status`.
- `tasks` — JEDNA tabela dla całej firmy (warunek widoków "moje taski");
  markery `lead:{id}` / `meeting:{id}` w opisie wiążą taski pipeline'ów.
- `activities` — append-only log, pisze WYŁĄCZNIE n8n; timeline leada + debug
  (`flow`, `payload` JSON, typ `automation_error`).
- `task_templates` (RRULE dla W1), `projects`, `testimonials` (biblioteka
  referencji, many-to-many z leads).

**Zasady projektowe:** ludzie zmieniają statusy tam, gdzie pracują — n8n
wykonuje robotę i pisze historię; automat NIGDY nie scala po cichu (auto-akcja
tylko przy dokładnym mailu, reszta = sugestia + task); decyzje przez pola
select, nie komentarze (komentarze nie triggerują webhooków w CE); guardy
stara/nowa wartość w każdym workflow na update (triggery per-pole są płatne).

## 6. Widoki (mapowanie na wymagania)

| Wymaganie | Realizacja |
|---|---|
| moje taski ze wszystkich projektów | `tasks` Grid per osoba (filtr assignee, locked) |
| kalendarz moich tasków | `tasks` Calendar po `due_date` per osoba |
| taski cykliczne | `task_templates` + W1 (cron n8n; workflows NocoDB płatne) |
| kanban etapów leadów | `leads` Kanban po `stage`, filtr `state=open` |
| dodaj lead ręcznie | `leads` Form view |
| kalendarz spotkań | `meetings` Calendar po `starts_at` |
| timeline leada | `activities` w expanded record leada |
| kolejka weryfikacji AI | `meetings` Grid, `processing_status=ai_draft_ready` |
| produkcja ofert | `leads` Kanban po `offer_prep_status` |

## 7. Automatyzacje n8n

| WF | Trigger | Funkcja |
|---|---|---|
| W1 | cron 06:00 | taski cykliczne z szablonów (RRULE: DAILY/WEEKLY;BYDAY/MONTHLY;BYMONTHDAY), idempotentny |
| W2 | leads update | kamienie milowe + state przy zmianie stage; task "uzupełnij powód utraty"; mail do ownera |
| W3 | tasks insert+update | powiadomienie mail do assignee (łata brak notyfikacji w NocoDB CE) |
| W4 v2 | 3 webhooki: Tally / CF7 / Bookings | adaptery → wspólna kaskada dopasowań (niżej) |
| W5 | leads insert | dedup firmy po domenie e-mail (lista domen publicznych!), pending_confirmation + komentarz; guard: pomija leady z już podlinkowaną firmą |
| W6a | meetings update | transkrypcja → OpenRouter → `ai_analysis` → weryfikacja; akceptacja → cele (routing B2B→Dorota / B2C→Aleksandra); braki/odrzuty → taski naprawcze |
| W6b | leads update | cele → referencje → walidacja linków → task "złóż ofertę" + `draft_ready` |

> Te workflowy **zastępują** `n8n-workflows/wf1-wf6*.json` (stary pipeline
> lead→discovery→audit→recommendation→offer z generowaniem PPTX) — te pliki
> zostają w repo jako historyczne, nieużywane. Importowalne wersje: `fable/W1_
> recurring_tasks.json` … `fable/W6b_offer_pipeline.json` + `fable/W4v2_
> intake_matching.json` (zastępuje `W4_new_lead_intake.json`), spakowane też
> w `fable/n8n_workflows_coaction.zip` z instrukcją placeholderów/webhooków
> (`fable/README.md`).

**Kaskada intake (W4 v2):** Tier 1 dokładny e-mail (jedyna auto-akcja: otwarty
lead → task "napisał ponownie" bez nowego leada; zamknięty → nowy lead,
`enquiry_no+1`, dziedziczenie firmy) → Tier 2 domena (delegowane do W5) →
Tier 3 imię+nazwisko/telefon po normalizacji (sugestia duplikatu, nigdy
auto-merge) → Tier 4 LLM jako EKSTRAKTOR kryteriów (maile/nazwiska/firmy
z treści; deterministyczne wyszukiwanie po ekstrakcji; `type_signal` dla B2B
z prywatnego maila) → Tier 5 czysty nowy lead + task "zaklasyfikuj".
Booking z MS Bookings zawsze tworzy meeting i linkuje do leada z kaskady.
Każdy przebieg loguje do `activities` (kryteria AI w payload).

**Integracje:** Tally (natywny webhook), Contact Form 7 (wymaga wtyczki
webhook na WP; mapa pól w adapterze), MS Bookings (przez Power Automate →
HTTP POST), OpenRouter (model konfigurowalny per env).

## 8. Migracja danych

`fable/import_legacy_excel.py`: Excel CEO → NocoDB. Selecty normalizowane do
realnych opcji; 12 kolumn dat → kamienie milowe + rekordy meetings (done);
planowane działania → otwarte taski; `enquiry_no` liczony z historii; pełny
surowy wiersz w payload activity (nic nie ginie); idempotencja po `legacy_id`.

> To inny import niż opisany w poprzedniej wersji PRD (1600 rekordów, layout
> kolumn `organizations/opportunities`) — ten kierunek nieaktualny, patrz
> historia wersji na górze dokumentu.

**Procedura:** pola `legacy_id`+`received_at` → `--dry-run` → uzupełnienie
STAGE_MAP wg raportu → wyłączenie W3/W4/W5 → import → włączenie workflowów.
Okres przejściowy: `legacy_crm_2.xlsx` — read-only lustro generowane od zera
z widoku SQL `legacy_crm_mirror` (Postgres → n8n → xlsx), układ kolumn 1:1 ze
starym Excelem + kolumna linków do rekordów NocoDB; sunset ~2 mies. po migracji.
(Widok SQL do napisania po migracji — czeka na `\dt`/`\d` z nowego Postgresa.)

## 9. Testy

Test Runner (pytest, katalog 63 przypadków w `fable/test_cases.md`): syntetyczne
payloady webhooków NocoDB → endpointy n8n → asercje przez API. ~25 przypadków
AUTO zaimplementowanych (guardy, kaskada, pułapki typu substring domen);
SEMI = LLM z asercjami strukturalnymi; PROC = importer przez dry-run.
Po migracji na 2 VPS-y: runner celuje w VPS-B (osobna instancja = koniec kopii
workflowów i prefiksów).

## 10. Artefakty projektu

Wszystkie poniższe pliki leżą w `fable/` (archiwum artefaktów z sesji projektowej
w przeglądarce Claude, 2026-07-17/18) — ten PRD jest ich podsumowaniem, nie
zastępuje szczegółów w źródłowych plikach.

| Plik | Zawartość |
|---|---|
| `fable/nocodb_crm_schema_v2.md` (+ `v1.md`, wcześniejsza iteracja) | pełny schemat 9 tabel + zasady |
| `fable/crm_flow.mermaid`, `fable/crm_erd.mermaid`, `fable/crm_intake_matching.mermaid` | diagramy: cykl życia leada, ERD, kaskada intake |
| `fable/W1..W6b*.json` + `fable/README.md` (`fable/n8n_workflows_coaction.zip`) | importowalne workflowy + instrukcja placeholderów/webhooków |
| `fable/W4v2_intake_matching.json` | intake 3 źródeł + kaskada (zastępuje W4) |
| `fable/W0_seed_sample_data.json`, `fable/seed_nocodb.py`, `fable/sample_data_overview.md` | dane przykładowe (2 drogi) + mapa relacji |
| `fable/import_legacy_excel.py` | migracja legacy z dry-run |
| `fable/test_runner_coaction.zip` (`fable/test_cases.md`, `fable/conftest.py`, `fable/test_workflows.py`, `fable/nocodb.py`) | katalog przypadków + harness pytest |
| `fable/meta.json` | eksport żywej struktury "CoAction TEST Base" z NocoDB (2026-07-17) — dowód, że model jest wdrożony, nie tylko zaprojektowany |

## 11. Znane ograniczenia i ryzyka

1. **Brak offsite backupu z realnym cronem/targetem na obu VPS-ach** — mechanizm
   (`backup/backup.sh`, restic+rclone) gotowy, ale konfiguracja crona na serwerach
   i wybór dostawcy (Backblaze B2 / Hetzner Storage Box) — otwarte, priorytet #1.
2. NocoDB CE: brak powiadomień push/apki mobilnej (łatane przez W3 mail),
   jedna aktywna sesja per konto (ryzyko UX telefon+laptop — do weryfikacji
   na bieżącej wersji), triggery per-pole płatne (stąd guardy), komentarze
   bez webhooków, filtrowane rollupy płatne (raporty → SQL na Postgresie).
3. Kształt payloadów webhooków NocoDB różni się między wersjami (pole User:
   obiekt/tablica) — guardy pisane defensywnie; po każdym upgrade NocoDB
   przebieg Test Runnera na VPS-B PRZED aktualizacją produkcji.
4. Tier 3/4 matchuje tylko otwarte leady i firmy (limit 200) — świadoma
   granica; przy skali setek zapytań/mies. → wyszukiwanie w Postgresie.
5. Wiązanie tasków pipeline'ów markerami w opisie — nie edytować ręcznie.
6. Seed i import nie są transakcyjne — seed tworzy duplikaty przy re-runie
   (importer nie, dzięki `legacy_id`).
7. **CPU passthrough i status MinIO OSS** — patrz §4; oba udokumentowane,
   pierwsze naprawione, drugie świadomie zamrożone bez docelowej decyzji.

## 12. Backlog (faza 2)

Tabela `offers` + generowanie oferty PPTX/www z pól `participants` i
`testimonials`; formularze przed-audytowe dla uczestników; AI-draft
`needs_summary` z transkrypcji; dashboard SQL (czas new→won, konwersja per
source, per branża); asercje mailowe w Test Runnerze (MailHog API); rozszerzenie
parsera RRULE (YEARLY/INTERVAL); wyszukiwanie po zamkniętej historii (Postgres
FTS); sunset lustra xlsx.

**Generowanie oferty jako plik (PPTX/PDF) — wraca do zakresu tylko po decyzji
klienta/CEO** (patrz §14). Poprzednia wersja PRD zawierała gotowy, szczegółowy
projekt tego serwisu — zachowany, nie stracony:
- Kontrakt `crm-api` (FastAPI + `python-pptx` + LibreOffice, bezstanowy,
  `POST /render`, `POST /template/inspect`, sieć `internal` bez portu w Caddy).
- Znane pułapki: podmiana tekstu w `runs` PowerPoint (merge przed replace),
  klonowanie slajdów celów (`python-pptx` bez natywnego API, `copy.deepcopy` XML;
  plan B: gotowe sloty + samo usuwanie), `soffice --convert-to pdf` (timeout,
  unikalny `-env:UserInstallation`, reap zombie procesów).
- `job_queue` w Postgresie (`FOR UPDATE SKIP LOCKED`, priorytety) jako zamiennik
  Redis/Celery, gdyby render miał być kolejkowany.
Ten materiał żyje wyłącznie w git history starej wersji tego pliku — do
wydobycia (`git log -- .ai/PRD.md`) w razie potwierdzenia potrzeby.

## 13. Status / najbliższe kroki

- [x] schemat, seed (przeszedł na realnej bazie), workflowy, importer, testy — dostarczone (patrz §10)
- [x] VPS-A (produkcja) i VPS-B (staging) wykupione i działają — pełny stack, 100% uptime
- [ ] Baza NocoDB modelu z §5 wdrożona i uzupełniona danymi na obu VPS-ach (dziś istnieje jako "CoAction TEST Base" — zweryfikować, czy to już VPS-A/B, czy osobne środowisko do przeniesienia)
- [ ] **backup offsite** (cron na serwerach + wybór dostawcy — patrz §11 pkt 1)
- [ ] podmiana placeholderów workflowów na ID z docelowej instancji (sed per VPS, patrz `fable/README.md`)
- [ ] wtyczka webhook CF7 na WordPressie + realny payload → mapa pól adaptera
- [ ] Power Automate dla Bookings → adapter
- [ ] dry-run importu na pełnym Excelu → STAGE_MAP → import na produkcji
- [ ] widok SQL `legacy_crm_mirror` + workflow lustra (po dostarczeniu `\dt`/`\d`)
- [ ] przebieg Test Runnera na VPS-B → poprawka builderów payloadów pod realną wersję NocoDB
- [ ] rollout zespołowy: pokaz `fable/crm_flow.mermaid`, widoki per osoba, data twardego cięcia
- [ ] rozstrzygnięcie otwartych pytań biznesowych, patrz §14

## 14. Otwarte pytania (do potwierdzenia z klientem/CEO)

1. **Generowanie oferty jako plik (PPTX/PDF)** — czy MVP kończy się na wycenionych,
   gotowych danych w NocoDB (`offer_prep_status=draft_ready`), czy klient
   oczekuje realnego pliku do wysyłki? Jeśli tak — wraca projekt `crm-api` z §12.
   Powiązane pytanie z poprzedniej wersji PRD: czy Przemek zaakceptuje, że NIE
   edytuje PPTX ręcznie (jeśli renderer wróci w zakres)?
2. **Offsite backup — gdzie?** Backblaze B2 (~$6/TB/mies.) czy Hetzner Storage
   Box (~€3/mies. za 1 TB)?
3. **Dostawca ASR** (transkrypcja spotkań, jeśli nagrania mają być automatycznie
   transkrybowane zamiast ręcznego wklejania) — Deepgram / AssemblyAI / OpenAI
   Whisper API?
4. **MinIO OSS: zamrożone na stałe czy migracja** na aktywnie rozwijaną
   alternatywę (Garage, SeaweedFS) — patrz §4/§11 pkt 7. Ma znaczenie głównie,
   jeśli powstanie integracja S3 SDK (np. renderer z pytania #1).
5. **Kto dostaje taski poza już zamodelowanymi rolami** — role Kasi (marketing)
   i Pauliny (finanse) są w §2, ale nie były jeszcze przetestowane na żywych
   danych/workflowach tak jak Przemek/Dorota/Aleksandra.
