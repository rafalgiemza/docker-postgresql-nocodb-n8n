# Plan wdrożenia — stan obecny → faza 1 (CoAction CRM)

Bazowane na `.ai/PRD.md` v2.0 (model NocoDB-native, `fable/` jako źródło szczegółów
schematu/workflowów/testów) — patrz tam sekcję "Historia wersji" na górze dokumentu
dla kontekstu, dlaczego ten plan wygląda inaczej niż wcześniej.

> **Zmiana kierunku (2026-07-17/18):** wcześniejsza wersja tego planu śledziła
> budowę znormalizowanego schematu Postgresa (`crm.v_offer_builder` i pochodne)
> pod serwis `crm-api` (renderer PPTX/PDF). Ten kierunek jest porzucony — NocoDB
> zarządza tabelami bezpośrednio (Creator UI na Postgresie), a generowanie pliku
> oferty jest dziś **otwartym pytaniem biznesowym**, nie potwierdzonym zakresem
> (`.ai/PRD.md` §12, §14). Poniższy plan śledzi stan wdrożenia modelu z `.ai/PRD.md`
> §5–§9 (9 tabel NocoDB, workflowy W1–W6b, Test Runner, import legacy).

---

## 1. Co już istnieje w repo (stan faktyczny, niezależny od modelu danych)

| Element | Stan | Plik |
|---|---|---|
| Hosting: 2× Sfera Host VPS PRO (VPS-A prod / VPS-B staging) | ✅ oba wykupione, pełny stack, 100% uptime — patrz `.ai/PRD.md` §4, `post-mortem/vps-migration-decision.md` | — |
| VPS hardening (ufw, fail2ban, ssh key-only, unattended-upgrades) | ✅ gotowe | `cloud-init.yaml` |
| Docker Compose: postgres, n8n(+runner), nocodb, MinIO(+init), MongoDB, LibreChat, Uptime Kuma, Beszel, Budibase, autoheal, caddy | ✅ działa, jeden `docker-compose.yml` dla obu VPS-ów, różnice tylko przez `.env` | `docker-compose.yml`, `fragments/*.yml` |
| 3 bazy w jednym Postgresie: `n8n`, `nocodb`, `appdata` | ✅ zgodne z `.ai/backups.md` | `scripts/init-data.sh`, `.env.example` |
| Caddy + TLS | ✅ gotowe, UAT na `giemza.dev`, prod (`coaction.pl`) czeka na DNS klienta | `Caddyfile` |
| Backup lokalny (`make backup`) | ✅ dumpuje role + `n8n`/`nocodb`/`appdata` + attachmenty NocoDB + mongodump do `./backups/` | `backup/backup.sh` |
| **Backup offsite (cron + target realny)** | ❌ mechanizm (`restic`+`rclone`) gotowy w skrypcie, ale cron na serwerach i wybór dostawcy nie dopięte — **priorytet #1** | `backup/backup.sh`, `.ai/PRD.md` §11/§14 |
| Dostęp NocoDB → `appdata` (schemat `crm`, `nocodb_crm_user` z `CREATE`+`USAGE`, `REVOKE CREATE ON SCHEMA public`) | ✅ zrobione | `scripts/init-data.sh` |
| LibreChat + MongoDB | ✅ gotowe, zero integracji z CRM | `docker-compose.yml`, `librechat.yaml` |
| MinIO + buckety (offers/templates/recordings/transcripts/backups + budibase-*) | ✅ gotowe | `scripts/minio-init.sh`, `fragments/minio.yml` |
| Uptime Kuma | ✅ monitoring wszystkich usług, interwał 30s od 2026-07-15 | `fragments/uptime-kuma.yml` |
| Beszel | ✅ monitoring zasobów per-kontener | `fragments/beszel.yml` |
| Budibase | ✅ dodany 2026-07-18, własny CouchDB+Redis, reużywa wspólne MinIO | `fragments/budibase.yml` |
| Sieci Docker segmentowane (`edge`/`internal`/`data`) | ❌ brak — jedna płaska sieć (nieblokujące: bez `crm-api` nie ma dziś serwisu wymagającego izolacji `internal`) | — |

## 2. Model danych CRM (NocoDB-native, `.ai/PRD.md` §5)

| Element | Stan |
|---|---|
| Schemat 9 tabel (`companies/leads/participants/meetings/tasks/activities/task_templates/projects/testimonials`) | ✅ zaprojektowany i **wdrożony jako żywa baza** — "CoAction TEST Base" w NocoDB, eksport struktury w `fable/meta.json` (2026-07-17) |
| Workflowy n8n W1–W6b (+ W4v2 kaskada intake) | ✅ dostarczone jako importowalne JSON-y, patrz `.ai/PRD.md` §7/§10 |
| Test Runner (63 przypadki, pytest) | ✅ dostarczony, patrz `.ai/PRD.md` §9 |
| Importer legacy Excel (`import_legacy_excel.py`) | ✅ dostarczony, dry-run jeszcze nie uruchomiony na pełnym pliku |
| Seed danych przykładowych (2 drogi: workflow W0 / skrypt Python) | ✅ dostarczony, przeszedł na realnej bazie |

**Do zweryfikowania:** czy "CoAction TEST Base" (`fable/meta.json`) to już baza na
VPS-B (staging), czy osobne, jeszcze nieprzeniesione środowisko — wpływa na to, ile
z poniższej FAZY 3 jest już zrobione na docelowej infrastrukturze vs. wymaga
migracji/powtórzenia.

## 3. Kolejność wdrożenia (skorygowana pod obecny stan)

### FAZA 1 — Domknięcie infrastruktury
1. ✅ 2× VPS PRO wykupione, stack wdrożony na obu (patrz §1)
2. ❌ Backup offsite: cron na serwerach + wybór dostawcy (Backblaze B2 / Hetzner Storage Box) — `.ai/PRD.md` §14 pkt 2
3. Domena `coaction.pl` w Caddy — mechanizm gotowy i przetestowany na UAT (`*.giemza.dev`), samo DNS czeka na klienta
4. Sieci Docker (`edge`/`internal`/`data`) — odłożone, bez aktualnego konsumenta (patrz §1)

### FAZA 2 — Model danych CRM (NocoDB-native)
1. ✅ Schemat 9 tabel zaprojektowany i wdrożony ("CoAction TEST Base")
2. ⚠️ Potwierdzić, czy ta baza żyje już na VPS-A/VPS-B docelowo, czy wymaga przeniesienia
3. ⚠️ Uzupełnienie danych produkcyjnych (import legacy Excel — patrz FAZA 5)

### FAZA 3 — Workflowy n8n (W1–W6b)
1. Podmiana placeholderów (ID tabel/pól, credentiale, adresy mailowe) per VPS —
   instrukcja gotowa w `fable/README.md` §1–3
2. Import kolejno **W3 → W2 → W1 → W4v2 → W5 → W6a → W6b** (powiadomienia najpierw,
   zgodnie z `fable/README.md` §4)
3. Webhooki NocoDB skonfigurowane z **"Include previous record"** — krytyczne dla
   guardów stara/nowa wartość
4. Smoke test scenariusza "Piotr" (`fable/README.md` §4) na VPS-B

### FAZA 4 — Test Runner na VPS-B
1. Uruchomienie przeciw VPS-B (osobna instancja n8n = koniec kopii workflowów `-TEST`
   i prefiksów ścieżek)
2. Korekta builderów payloadów pod realną wersję NocoDB (kształt payloadu webhooków
   różni się między wersjami — `.ai/PRD.md` §11 pkt 3)

### FAZA 5 — Migracja legacy Excel
1. Pola `legacy_id`+`received_at` na tabeli `leads`
2. `import_legacy_excel.py --dry-run` → raport rozbieżności → uzupełnienie STAGE_MAP
3. Wyłączenie W3/W4v2/W5 na czas importu → import → włączenie workflowów
4. Uruchomienie lustra `legacy_crm_2.xlsx` (widok SQL `legacy_crm_mirror` — do
   napisania po dostarczeniu `\dt`/`\d` z docelowego Postgresa)

### FAZA 6 — Integracje zewnętrzne
1. Wtyczka webhook Contact Form 7 na WordPressie + mapa pól adaptera (realny payload)
2. Power Automate dla MS Bookings → adapter HTTP POST

### FAZA 7 — Rollout zespołowy
1. Pokaz `fable/crm_flow.mermaid`, widoki per osoba
2. Ustalenie daty twardego cięcia z Asany/Excela
3. Szkolenie: NocoDB (codziennie), n8n (rozszerzanie), interpretacja `activities`

### FAZA 8 (backlog, warunkowa) — Renderer ofert PPTX/PDF
Wraca do zakresu tylko po decyzji klienta/CEO (`.ai/PRD.md` §14 pkt 1). Projekt
`crm-api` z poprzedniej wersji PRD jest gotowy do wskrzeszenia — pułapki
LibreOffice/`python-pptx`, kontrakt API i `job_queue` opisane w `.ai/PRD.md` §12
i w git history starszej wersji tego pliku.

---

## 4. Otwarte pytania

Przeniesione i skonsolidowane w `.ai/PRD.md` §14 (generowanie PPTX/PDF, offsite
backup, dostawca ASR, przyszłość MinIO OSS, role Kasi/Pauliny) — nie duplikować tu,
tylko odsyłać.

Specyficzne dla wdrożenia (nie biznesowe):
1. dbmate czy inne narzędzie migracji dla ewentualnego przyszłego SQL (widoki,
   triggery) — nieblokujące, odłożone do momentu, gdy powstanie pierwszy ręczny SQL
   wymagający wersjonowania.
2. Czy "CoAction TEST Base" (`fable/meta.json`) ma zostać przeniesiona 1:1 na VPS-A/B,
   czy odtworzona od zera na docelowej infrastrukturze — do ustalenia przed FAZĄ 3.
