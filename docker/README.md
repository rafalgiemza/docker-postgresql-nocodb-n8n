# n8n with PostgreSQL

Starts n8n and NocoDB, sharing one PostgreSQL instance (separate database/user each).

## Start

To start n8n with PostgreSQL simply start docker-compose by executing the following
command in the current folder.

**IMPORTANT:** But before you do that change the default users and passwords in the [`.env`](.env) file!

```
docker-compose up -d
```

To stop it execute:

```
docker-compose stop
```

## Configuration

The default name of the database, user and password for PostgreSQL can be changed in the [`.env`](.env) file in the current directory.

## MinIO — załączniki/awatary NocoDB (PRD §1.1/§8.5)

Zero kroków ręcznych — `make up` wystarcza. `minio-init` (one-shot, patrz `minio-init.sh`) tworzy przy starcie buckety (`offers`/`templates` z versioningiem, `recordings`/`transcripts`/`backups`) oraz rolę `nocodb` ograniczoną wyłącznie do bucketu `attachments` (nigdy root `MINIO_ROOT_USER`). `nocodb` w compose ma już wpięte `NC_S3_*` na tę rolę — pole typu Attachment (i avatar użytkownika) w NocoDB działa od razu, bez konfiguracji w UI.

**Gotcha, jeśli będziesz to kiedyś zmieniał:** NocoDB nie proxuje pobierania załączników przez siebie — zwraca przeglądarce bezpośredni, podpisany link do `NC_S3_ENDPOINT`. Dlatego `MINIO_ENDPOINT` musi być tym samym, publicznie rozwiązywalnym adresem co dla przeglądarki (`https://${MINIO_HOST}`), a jednocześnie osiągalnym z kontenera `nocodb`. Rozwiązane network aliasem `${MINIO_HOST}` na serwisie `caddy` — kontener rozwiązuje tę nazwę na Caddy'ego przez wewnętrzne DNS Dockera, przeglądarka przez publiczne DNS; oba trafiają do tego samego Caddy'ego → `minio:9000`. W deweloperskim `docker-compose.override.yml` ominięte prościej: port MinIO publikowany na hosta, `NC_S3_ENDPOINT=http://localhost:9000`.

**Prod:** wymaga rekordu DNS dla `MINIO_HOST` (`minio.<domena>`) wskazującego na ten sam adres VPS co `N8N_HOST`/`NC_HOST` — bez niego Caddy nie wystawi certu i podgląd/pobieranie załączników w NocoDB będzie martwe (upload i tak zadziała, bo idzie przez backend NocoDB, nie przez przeglądarkę).

## FAZA 3 — Offer Builder (n8n + NocoDB)

Runbook dla `.ai/IMPLEMENTATION_PLAN.md` FAZA 3. Zakłada, że `make migrate` i `make seed` już przeszły (widoki `crm.v_*`, role `nocodb_crm_user`/`n8n_crm_user`, dane referencyjne).

### 1. Dane demo/testowe

`crm.v_offer_builder` wspiera tylko `SELECT`/`UPDATE`, nie `INSERT` — bez fixture'a nie ma czego otworzyć w NocoDB. `make seed-demo` (`app_seed_demo.sh` → `seed_demo.sql`) zakłada jedną kompletną ofertę demo (`organizations.name = 'Demo Sp. z o.o.'`, offer_items 60h + 15h) i jest bezpiecznie re-runnable — czyści poprzedni demo-rekord przed insertem. **Nie** to samo co `make seed` (dane referencyjne z cennikiem/testimonialami) — to jednorazowy fixture, decyzja o pozostawieniu/usunięciu przed produkcją zapada w FAZIE 6.

```
make seed-demo
```

### 2. n8n: credential do `appdata`

W n8n UI → Credentials → New → Postgres:
- Host: `postgres`, Database: wartość `APP_DB` z `.env` (domyślnie `appdata`)
- User/Password: `N8N_CRM_USER`/`N8N_CRM_PASSWORD` z `.env`
- Nazwa credentiala: `appdata (n8n_crm_user)` (tak nazywa się placeholder w WF-6, patrz niżej)

Ta rola widzi wyłącznie `crm.v_offer_builder` (`SELECT, UPDATE` — schema.sql sekcja 15) — świadomie węższy zakres niż `nocodb_crm_user`.

### 3. WF-6 okrojone — import

[`n8n-workflows/wf6-zatwierdz-oferte.json`](n8n-workflows/wf6-zatwierdz-oferte.json) to gotowy do importu workflow: `Webhook (POST /webhook/zatwierdz-oferte)` → `Postgres: UPDATE crm.v_offer_builder SET status='ready' WHERE offer_id = $1` → `Respond to Webhook`. Zweryfikowany lokalnie przez `n8n import:workflow` (n8n 2.27.5) — importuje się bez ostrzeżeń o wersjach node'ów.

Import: n8n UI → Workflows → **Import from File** → wybierz plik. Po imporcie:
1. Podepnij pod node `Postgres: Zatwierdź ofertę` credential z kroku 2 (placeholder `REPLACE_W_UI` w pliku wymaga ręcznego przypisania — to nie jest błąd, to celowe: sekrety nie idą do Gita).
2. Aktywuj workflow.
3. W NocoDB spiąć przycisk `Zatwierdź ofertę` (krok 4) z webhookiem tego workflowa.

**Uwaga o UPDATE:** nie trzeba przepisywać wszystkich kolumn w `SET` — Postgres dla widoku z `INSTEAD OF UPDATE` sam wypełnia `NEW.*` wartościami z bieżącego wiersza dla kolumn pominiętych w `SET`. Zweryfikowane bezpośrednio na bazie: `UPDATE crm.v_offer_builder SET status = 'sent' WHERE offer_id = X` zostawia `item1_hours`/`total_price_pln` nietknięte.

### 4. Git sync workflowów (Community Edition — bez natywnego Source Control)

n8n self-hosted w tym projekcie to Community Edition — natywny Git sync (Settings → Source Control) jest funkcją Enterprise/Cloud i tu niedostępny. Wersjonowanie workflowów robimy ręcznym eksportem do repo:

```
docker exec docker-n8n-1 n8n export:workflow --all --output=/tmp/workflows/
docker cp docker-n8n-1:/tmp/workflows/. n8n-workflows/
```

Robić to po każdej sensownej zmianie workflowa w UI i commitować `docker/n8n-workflows/*.json` normalnie.

### 5. NocoDB: widok „Offer Builder"

Baza zewnętrzna w NocoDB → appdata przez `nocodb_crm_user` (host `postgres`, port `5432`, dane z `.env`: `NOCODB_CRM_USER`/`NOCODB_CRM_PASSWORD`, schema `crm`). Widok na `v_offer_builder` (+ linked `v_offer_goals`, `v_testimonials`) z polami wg PRD §5, **okrojony** o to, co nie istnieje bez renderera:

| Pole NocoDB | Kolumna widoku | Uwagi |
|---|---|---|
| `Imię i nazwisko` | `first_name`, `last_name` | |
| `Poziom: *` (5 pól) | `cefr_overall/range/accuracy/fluency/communicativeness` | read-only w praktyce — pochodzą z audytu, nie z tego widoku (edycja przez `v_audit_scores`) |
| `Opis sytuacji` | `situation_description` | |
| `Nagłówek rekomendacji` | `headline` | |
| `Wariant 1: produkt/godziny/cena` | `item1_product/item1_hours/item1_price_pln` | `item1_price_pln` **read-only** (trigger PG) |
| `Wariant 2: …` | `item2_*` | jw. |
| `Razem godzin` / `Razem cena` | `total_hours` / `total_price_pln` | **read-only**, trigger PG (`recalc_offer_totals`) |
| `Cele szkoleniowe` | linked `v_offer_goals` po `recommendation_id` | |
| `Testimoniale` | linked `v_testimonials` (multi, `included_testimonial_ids`) | |
| **`[Zatwierdź ofertę]`** | — | Button → webhook WF-6 (krok 3), **zastępuje** `[Generuj ofertę]` z PRD §5 |

**Pominięte na razie** (poza zakresem MVP, patrz IMPLEMENTATION_PLAN.md §6): `Szablon`, `Status generowania`, `⬇ PPTX`/`⬇ PDF`.

### 6. Test pętli end-to-end (kryterium akceptacji FAZY 3)

Na rekordzie z `make seed-demo`: zmień `Wariant 1: godziny` z `60` na `45` (wybierz odpowiedni `pricing_tier` z cennika 45h) → `Razem cena`/`Razem godzin` przeliczają się natychmiast (trigger PG, nie n8n) → kliknij `Zatwierdź ofertę` → `status` w bazie zmienia się na `ready`. Zweryfikowane manualnie przez `psql` na widoku (60h→45h: 20400.00 PLN → 16500.00 PLN); pozostaje powtórzyć to samo klikając w UI NocoDB.