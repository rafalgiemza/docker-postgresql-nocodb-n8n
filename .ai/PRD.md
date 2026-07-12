# Plan wdrożenia — CRM CoAction (MVP: lead → offer)

**Target:** Mikrus 4.1 Pro — 2 vCPU, 8 GB RAM, 80 GB NVMe, Finlandia, Debian/Ubuntu
**Zakres MVP:** pipeline od leada do wygenerowanej oferty (PPTX + PDF)
**Data:** lipiec 2026

---

## 1. Architektura — decyzje finalne

### 1.1 Stack

| Usługa | Wersja | Rola | RAM idle |
|---|---|---|---|
| **Caddy** | 2.x | TLS (auto Let's Encrypt), reverse proxy, jedyny publiczny port | 30 MB |
| **PostgreSQL** | 16 | **Źródło prawdy.** Dane CRM, kolejka jobów, logika cenowa | 1 200 MB |
| **PgBouncer** | 1.22+ | Connection pooling (transaction mode) | 20 MB |
| **n8n** | latest | **Orchestracja.** Triggery, sekwencje, AI, scheduler, retry | 700 MB |
| **NocoDB** | latest | **Jedyne UI dla klienta.** Grid, kanban, Button fields | 450 MB |
| **crm-api** | custom | Renderer: `POST /render` → PPTX + PDF. Bezstanowy | 150 MB / **900 peak** |
| **MinIO** | latest | Pliki, szablony `.potx`, snapshoty ofert (versioning ON) | 300 MB |
| **LibreChat** | latest | Czat AI dla zespołu (osobny byt, zero integracji z CRM w MVP) | 600 MB |
| **MongoDB** | 7 | **Wyłącznie dla LibreChat.** Zero danych CRM | 500 MB |
| **Uptime Kuma** | latest | Monitoring | 120 MB |
| **RAZEM idle** | | | **~4 070 MB** |
| **PEAK (render)** | | | **~4 820 MB** |
| **Wolne z 8 GB** | | | **~3.2 GB** |

**Odrzucone świadomie:**
- ❌ **Appsmith** — 1.8 GB stałego RAM (Java+Mongo+Redis+Nginx). Brak w MVP. Wraca, gdy NocoDB okaże się za surowy (live preview oferty).
- ❌ **Hono / Node** — drugi runtime bez uzasadnienia. Python obsługuje i API, i render.
- ❌ **Gotenberg** — LibreOffice w `crm-api` robi PDF z tego samego źródła co PPTX (gwarancja zgodności wizualnej).
- ❌ **Redis / Celery** — kolejka w Postgresie (`FOR UPDATE SKIP LOCKED`).

### 1.2 Diagram

```
                        INTERNET
                            │
                    ┌───────▼────────┐
      Cal.com ─────►│  Caddy :443    │◄──── użytkownicy
      (webhook)     │  TLS, proxy    │      (NocoDB, n8n UI, LibreChat)
                    └───────┬────────┘
                            │
        ┌──────────┬────────┼────────┬──────────┬──────────┐
        ▼          ▼        ▼        ▼          ▼          ▼
     NocoDB       n8n   LibreChat  MinIO   Uptime Kuma   (crm-api
     (UI)     (logika)  (AI chat) (S3+web)              NIE wystawiony)
        │          │        │        ▲
        │          │        │        │
        │          ├────────┼────────┘
        │          │        │
        │          │        └──────────► MongoDB  (${MONGO_URI})
        │          │                     [ready-to-migrate]
        │          │
        │          └── HTTP (net: internal) ──► crm-api
        │                                        (FastAPI + python-pptx
        │                                         + LibreOffice)
        │                                            │
        └──────────────┬─────────────────────────────┘
                       ▼
                  PgBouncer :6432
                       │
                       ▼
                PostgreSQL :5432
              (bind 127.0.0.1 only)
```

**Sieci Dockera:**

| Sieć | Kto | Uwagi |
|---|---|---|
| `edge` | caddy, nocodb, n8n, librechat, minio, uptime-kuma | Ruch przez Caddy |
| `internal` | n8n, crm-api, pgbouncer, minio | **Nie ma dostępu do Caddy.** crm-api tylko tu |
| `data` | pgbouncer, postgres | Postgres widoczny **wyłącznie** dla PgBouncer |
| `mongo` | librechat, mongodb | Izolacja — ready-to-migrate |

`crm-api` **nie ma portu wystawionego przez Caddy.** Dostępny tylko dla n8n w sieci `internal`. Zero auth, zero rate-limitu do konfiguracji, zero powierzchni ataku.

### 1.3 Podział odpowiedzialności

| Warstwa | Co robi | Kto dotyka |
|---|---|---|
| **Postgres** | Stan, relacje, **walidacja (CHECK/FK)**, **logika cenowa (trigger)**, audit trail, kolejka jobów | Ty (migracje w Git) |
| **n8n** | Triggery, sekwencje, AI, notyfikacje, task creation, scheduler | Ty → **potem klient** |
| **NocoDB** | Grid, kanban, formularze, Button fields | **Klient codziennie** |
| **crm-api** | `POST /render` — funkcja czysta `JSON → {pptx, pdf}` | Ty, przy zmianie szablonu |

> **Reguła:** logika cenowa **NIE** żyje w n8n. Klient będzie edytował workflowy — cena musi być broniona przez bazę (`FK → pricing_tiers` + trigger przeliczający `total_price_pln`).

---

## 2. Model danych (Postgres)

### 2.1 Enumy

```
client_type      : B2B | B2C
lead_source      : google | referral | linkedin | website | inbound_call | partner | other
contact_form     : booking | email | phone | form | walk_in
lead_qualif      : MQL | SQL | DISQUALIFIED | UNQUALIFIED
opp_stage        : nowa | badanie_potrzeb | demo | przygotowanie_oferty | oferta_wyslana
                 | omowienie_oferty | umowa_wyslana | umowa_podpisana | utracona | archiwum
opp_state        : otwarta | zamknieta | wstrzymana
task_status      : todo | in_progress | blocked | done | cancelled
transcript_src   : manual_paste | asr_auto | upload_file
offer_status     : draft | ready | sent | accepted | rejected | superseded
rec_type         : business_english | english_for_it | english_plus_skills | skills_only | mixed
lesson_format    : 1-1 | pair | group
job_status       : queued | running | done | failed
```

### 2.2 Tabele — rdzeń

**`organizations`** — firma (NULL dla czystego B2C)

| Kolumna | Typ | Uwagi |
|---|---|---|
| `id` | `bigserial PK` | |
| `name` | `text NOT NULL` | |
| `industry` | `text` | "Software Development" |
| `size_bucket` | `text` | `<50` / `50-250` / `250+` |
| `nip` | `text` | |
| `business_context` | `jsonb` | AI-extracted: procesy, role, odbiorcy |
| `created_at` | `timestamptz DEFAULT now()` | |

**`people`** — osoba fizyczna (kontakt LUB uczestnik; w B2C to ta sama osoba)

| Kolumna | Typ | Uwagi |
|---|---|---|
| `id` | `bigserial PK` | |
| `organization_id` | `bigint FK NULL` | |
| `first_name`, `last_name` | `text` | |
| `email` | `citext` | partial UNIQUE gdzie `NOT NULL` |
| `phone` | `text` | |
| `job_title` | `text` | "Senior Frontend Developer" |
| `linkedin_url` | `text` | |
| `created_at` | `timestamptz` | |

**`clients`** — konto handlowe

| Kolumna | Typ | Uwagi |
|---|---|---|
| `id` | `bigserial PK` | **1638, 1639** — dla migrowanych rekordów wstawiane explicit (potem `setval` na sekwencji) |
| `type` | `client_type NOT NULL` | |
| `organization_id` | `bigint FK NULL` | |
| `primary_contact_id` | `bigint FK → people` | |
| `owner_user_id` | `bigint FK → users` | handlowiec (Przemek) |
| `source` | `lead_source` | |
| `contact_form` | `contact_form` | |
| `qualification` | `lead_qualif` | |
| `disqualification_reason` | `text` | |
| `minio_prefix` | `text` | `clients/1638/` |
| `inbound_at` | `timestamptz` | data + godzina wpłynięcia |
| `created_at` | `timestamptz` | |

**`opportunities`** — szansa sprzedaży (serce pipeline'u)

| Kolumna | Typ | Uwagi |
|---|---|---|
| `id` | `bigserial PK` | |
| `client_id` | `bigint FK NOT NULL` | |
| `stage` | `opp_stage NOT NULL DEFAULT 'nowa'` | |
| `state` | `opp_state NOT NULL DEFAULT 'otwarta'` | |
| `value_pln` | `numeric(10,2)` | |
| `label` | `text` | etykieta z Excela |
| `next_action_at` | `date` | |
| `next_action` | `text` | |
| `loss_reason` | `text` | |
| `notes` | `text` | |
| `created_at`, `updated_at` | `timestamptz` | |

> **⚠️ Daty etapów NIE jako kolumny.** W legacy Excelu było 11 kolumn `Data_*` (`Data szansy sprzedaży`, `Data DEMO`, `Data wysłania oferty`…). To antywzorzec — każdy nowy etap = migracja schematu.

**`opportunity_stage_history`** — audit trail; **wszystkie daty za darmo**

| Kolumna | Typ |
|---|---|
| `id` | `bigserial PK` |
| `opportunity_id` | `bigint FK` |
| `from_stage` | `opp_stage NULL` |
| `to_stage` | `opp_stage NOT NULL` |
| `changed_by` | `bigint FK → users NULL` (NULL = system/n8n) |
| `changed_at` | `timestamptz DEFAULT now()` |
| `note` | `text` |

Wypełniane **triggerem** `AFTER UPDATE OF stage ON opportunities`.
Widok `v_opportunity_dates` pivotuje to do płaskiej postaci **1:1 z legacy Excelem** → NocoDB pokazuje znajomy układ, baza jest czysta.

### 2.3 Discovery i transkrypcje

**`discovery_calls`**

| Kolumna | Typ | Uwagi |
|---|---|---|
| `id` | `bigserial PK` | |
| `opportunity_id` | `bigint FK` | |
| `scheduled_at`, `ended_at` | `timestamptz` | |
| `duration_min` | `int` | |
| `external_event_id` | `text` | ID z Cal.com |
| `meeting_url` | `text` | |
| `attendees` | `jsonb` | |

**`transcripts`**

| Kolumna | Typ | Uwagi |
|---|---|---|
| `id` | `bigserial PK` | |
| `discovery_call_id` | `bigint FK NULL` | |
| `audit_id` | `bigint FK NULL` | audyt też bywa nagrywany |
| `source` | `transcript_src` | |
| `language` | `text[]` | `{pl,en}` — **mieszane!** |
| `raw_text` | `text` | surowy transkrypt |
| `curated_text` | `text` | po korekcie handlowca |
| `recording_file_id` | `bigint FK → files NULL` | |
| `search_tsv` | `tsvector GENERATED` | `to_tsvector('simple', coalesce(curated_text, raw_text))` |
| `created_at` | `timestamptz` | |

> **`'simple'`, nie `'polish'`** — transkrypty są dwujęzyczne (patrz 1639: polski wywiad + angielska próbka mowy). Stemmer polski zniszczy terminy techniczne EN. Potrzebujesz lepszego FTS → `pg_trgm` + GIN.

**`extractions`** — output AI, **osobno od danych zatwierdzonych przez człowieka**

| Kolumna | Typ | Uwagi |
|---|---|---|
| `id` | `bigserial PK` | |
| `transcript_id` | `bigint FK` | |
| `model` | `text` | `claude-sonnet-4-6` |
| `prompt_version` | `text` | **krytyczne** — prompty będą się zmieniać |
| `payload` | `jsonb NOT NULL` | ustrukturyzowany output |
| `accepted_by` | `bigint FK → users NULL` | |
| `accepted_at` | `timestamptz NULL` | **brama** |
| `created_at` | `timestamptz` | |

Kontrakt `payload` (wymuszony JSON Schema w promptcie):

```json
{
  "client_goals": ["odzyskać płynność mówienia", "precyzja techniczna"],
  "challenges": ["upraszczanie wypowiedzi przy braku zwrotu", "napięcie pod presją"],
  "communication_situations": ["statusy projektowe", "decyzje architektoniczne"],
  "business_context": { "industry": "Software Development",
                        "role": "Senior Frontend Developer",
                        "international_scope": true },
  "participant_type": "individual_contributor",
  "hypothesis_recommendation": "english_for_it",
  "missing_data": ["budżet", "preferowana intensywność"],
  "confidence": 0.82
}
```

> **AI proponuje, człowiek zatwierdza.** Nic z `extractions` nie trafia do `opportunities`, dopóki `accepted_at IS NOT NULL`. To Twoja ochrona przed halucynacją w ofercie za 11 250 PLN.

### 2.4 Audyt i rekomendacja

**`participants`**

| Kolumna | Typ |
|---|---|
| `id` | `bigserial PK` |
| `client_id` | `bigint FK` |
| `person_id` | `bigint FK → people` |
| `manager_needs` | `text` |
| `self_assessment` | `jsonb` |
| `communication_situations` | `text[]` |

**`audits`**

| Kolumna | Typ | Uwagi |
|---|---|---|
| `id` | `bigserial PK` | |
| `participant_id` | `bigint FK` | |
| `opportunity_id` | `bigint FK` | |
| `auditor_user_id` | `bigint FK` | Ola / Dorota |
| `conducted_at` | `timestamptz` | |
| `observations` | `text` | |
| `strengths`, `gaps` | `text[]` | |
| `scope` | `jsonb` | |
| `status` | `text` | `planned` / `done` |

**`audit_scores`** — **dokładnie 5 wymiarów z obu decków**

| Kolumna | Typ | Uwagi |
|---|---|---|
| `id` | `bigserial PK` | |
| `audit_id` | `bigint FK` | |
| `dimension` | `text` | `overall` / `range` / `accuracy` / `fluency` / `communicativeness` |
| `cefr_level` | `text` | `B2` |
| `cefr_decimal` | `numeric(2,1)` | `0.6` → render: **`B2.6`** |
| `cefr_numeric` | `numeric GENERATED` | A1=1.0 … C2=6.0 + decimal |
| `justification` | `text` | |

`UNIQUE (audit_id, dimension)`

**`cefr_numeric` daje za darmo:** sortowanie, „pokaż wszystkich poniżej B2", progres w czasie (moduł 2.0), automatyczne triggery rekomendacji.

**`recommendations`**

| Kolumna | Typ | Uwagi |
|---|---|---|
| `id` | `bigserial PK` | |
| `opportunity_id` | `bigint FK` | |
| `audit_id` | `bigint FK NULL` | |
| `type` | `rec_type` | |
| `headline` | `text` | „MIĘDZYNARODOWA KOMUNIKACJA BIZNESOWA…" (slajd 4) |
| `situation_description` | `text` | **slajd 3** — draft AI + korekta metodyka |
| `rationale` | `text` | |
| `priority` | `int` | |
| `approved_by` | `bigint FK NULL` | |
| `approved_at` | `timestamptz NULL` | **brama do oferty** |

**`recommendation_goals`** — slajdy 5–7, zmienna liczba

| Kolumna | Typ |
|---|---|
| `id` | `bigserial PK` |
| `recommendation_id` | `bigint FK` |
| `position` | `int` |
| `title` | `text` |
| `body` | `text` |
| `stage_label` | `text` — `"ETAP 1: Business English 60h"` |

### 2.5 Oferta

**`pricing_tiers`** — cennik ze slajdu 8, **wersjonowany, nie hardcode**

| Kolumna | Typ | Przykład |
|---|---|---|
| `id` | `bigserial PK` | |
| `product` | `text` | `business_english` / `english_for_it` / `workshop` |
| `hours` | `int` | `60` |
| `format` | `lesson_format` | `1-1` |
| `price_pln` | `numeric(10,2)` | `11250.00` |
| `valid_from` | `date NOT NULL` | |
| `valid_to` | `date NULL` | NULL = aktualny |

Seed z decku: 15h=3750/4500, 30h=6375/7200, 60h=11250/13500, 120h=21000/25800, warsztat 15h=5600/7800.

**`offer_templates`** — **szablony w MinIO**

| Kolumna | Typ | Uwagi |
|---|---|---|
| `id` | `bigserial PK` | |
| `name` | `text` | „CoAction B2C indywidualny" |
| `variant` | `text` | `b2c` / `b2b` / `continuation` / `special` |
| `minio_key` | `text` | `templates/coaction_b2c_v3.potx` |
| `version` | `int` | |
| `placeholder_manifest` | `jsonb` | lista placeholderów wykrytych przy uploadzie |
| `slide_map` | `jsonb` | `{"goals_slide_idx": 4, "testimonial_slides": [11,12,...]}` |
| `active` | `boolean` | |
| `uploaded_by` | `bigint FK` | |
| `created_at` | `timestamptz` | |

> **`placeholder_manifest` jest kluczowy.** Przy uploadzie szablonu n8n woła `POST /template/inspect` → `crm-api` skanuje `.potx`, zwraca listę znalezionych `{{...}}`. Jeśli klient wgra szablon bez `{{cefr_overall}}`, dowiaduje się **od razu**, a nie przy pierwszej ofercie u klienta.

**`offers`**

| Kolumna | Typ | Uwagi |
|---|---|---|
| `id` | `bigserial PK` | |
| `opportunity_id` | `bigint FK` | |
| `recommendation_id` | `bigint FK` | |
| `template_id` | `bigint FK → offer_templates` | |
| `version` | `int NOT NULL` | `UNIQUE(opportunity_id, version)` |
| `status` | `offer_status` | |
| `total_hours` | `int` | **GENERATED / trigger** |
| `total_price_pln` | `numeric(10,2)` | **trigger — nigdy z frontu** |
| `discount_pct` | `numeric(4,2) DEFAULT 0` | |
| `valid_until` | `date` | |
| `included_testimonial_ids` | `bigint[]` | selekcja ze slajdów 12–24 |
| `included_sections` | `text[]` | które statyczne bloki włączyć |
| `custom_notes` | `text` | |
| `created_by` | `bigint FK` | |
| `created_at` | `timestamptz` | |

**`offer_items`** — oferta 1638 ma **DWA** komponenty (60h BE + 15h warsztat)

| Kolumna | Typ | Uwagi |
|---|---|---|
| `id` | `bigserial PK` | |
| `offer_id` | `bigint FK` | |
| `position` | `int` | |
| `product` | `text` | |
| `label` | `text` | „Business English – 60 godzin (2x60 min lub 1x90 min)" |
| `hours` | `int` | |
| `format` | `lesson_format` | |
| `pricing_tier_id` | `bigint FK → pricing_tiers` | **FK broni przed 150h spoza cennika** |
| `unit_price_pln` | `numeric(10,2)` | **kopiowane z tier przez trigger** |

**Trigger cenowy** (`BEFORE INSERT OR UPDATE ON offer_items`):
1. `unit_price_pln := (SELECT price_pln FROM pricing_tiers WHERE id = NEW.pricing_tier_id)`
2. `AFTER` → przelicz `offers.total_hours`, `offers.total_price_pln` (suma items × `(1 - discount_pct/100)`)

**Cena nigdy nie przychodzi z NocoDB ani n8n. Baza liczy sama.**

**`testimonials`** — slajdy 12–24, wybieralne

| Kolumna | Typ | Uwagi |
|---|---|---|
| `id` | `bigserial PK` | |
| `author` | `text` | „Michał Piórkowski" |
| `role` | `text` | „CEO & Cofounder" |
| `quote` | `text` | |
| `tags` | `text[]` | `{it, b2b, ceo}` — dla dopasowania |
| `slide_template_idx` | `int` | który slajd w `.potx` |
| `active` | `boolean` | |

> **Drugi moment „aha" dla Przemka:** dla developera IT wybiera Piórkowskiego + Kirejczyka (CEO software house'ów), dla HRBP — Gojtowską + Koniuszy. Dziś robi to **ręcznie kasując slajdy**. To realny ból, który zdejmujesz.

**`offer_snapshots`** — **immutable**

| Kolumna | Typ | Uwagi |
|---|---|---|
| `id` | `bigserial PK` | |
| `offer_id` | `bigint FK` | |
| `version` | `int` | mirror `offers.version` w chwili generowania |
| `format` | `text` | `pptx` / `pdf` |
| `minio_key` | `text` | `offers/1638/v2.pptx` |
| `sha256` | `text` | wykrywanie manipulacji |
| `payload_snapshot` | `jsonb` | **pełny JSON użyty do generowania** |
| `template_id` | `bigint FK` | którym szablonem renderowano |
| `template_version` | `int` | |
| `status` | `job_status` | `queued` → `running` → `done` / `failed` |
| `error` | `text` | |
| `generated_at` | `timestamptz` | |

> **`payload_snapshot` to Twoja polisa.** Za rok klient zapyta „co dokładnie zaoferowaliśmy 1638?" — dostaniesz odpowiedź, nawet jeśli MinIO padnie i cennik się zmienił.

### 2.6 Taski i kolejka

**`tasks`** — polimorficzne (etap procesu → task dla osoby)

| Kolumna | Typ | Uwagi |
|---|---|---|
| `id` | `bigserial PK` | |
| `entity_type` | `text` | `opportunity` / `audit` / `offer` / `transcript` |
| `entity_id` | `bigint` | |
| `assignee_user_id` | `bigint FK` | |
| `title` | `text` | „Wklej transkrypcję — 1638" |
| `stage_ref` | `opp_stage` | z którego etapu wynika |
| `status` | `task_status` | |
| `due_at` | `timestamptz` | |
| `payload` | `jsonb` | pola potrzebne **tylko na tym etapie** |
| `created_at`, `completed_at` | `timestamptz` | |

**`job_queue`** — kolejka z priorytetami (**zamiast Redis/Celery**)

| Kolumna | Typ | Uwagi |
|---|---|---|
| `id` | `bigserial PK` | |
| `kind` | `text` | `render_offer` / `ai_extract` / `asr` |
| `priority` | `int` | **10** = interaktywne, **3** = AI, **1** = batch |
| `payload` | `jsonb` | |
| `status` | `job_status` | |
| `attempts` | `int DEFAULT 0` | |
| `last_error` | `text` | |
| `locked_at` | `timestamptz` | |
| `created_at` | `timestamptz` | |

Konsument (n8n lub worker):
```sql
SELECT * FROM job_queue
WHERE status = 'queued'
ORDER BY priority DESC, created_at ASC
LIMIT 1
FOR UPDATE SKIP LOCKED;
```

**Jeden konsument = brak równoległych LibreOffice = semafor za darmo.**

**`files`** — referencje MinIO

| Kolumna | Typ |
|---|---|
| `id` | `bigserial PK` |
| `bucket` | `text` |
| `key` | `text` |
| `mime` | `text` |
| `size_bytes` | `bigint` |
| `sha256` | `text` |
| `uploaded_by` | `bigint FK` |
| `created_at` | `timestamptz` |

### 2.7 Widoki dla NocoDB

NocoDB **nie dotyka tabel bazowych.** Pracuje na widokach, przez usera z ograniczonym `GRANT`.

| Widok | Zawiera | Uprawnienia |
|---|---|---|
| `v_pipeline` | opportunity + client + person + stage + daty (pivot z historii) | `SELECT, UPDATE(stage, next_action, notes)` |
| `v_offer_builder` | **pola 1:1 ze slajdami** (patrz §5) | `SELECT, UPDATE` (bez cen!) |
| `v_offer_goals` | cele szkoleniowe (linked) | `SELECT, INSERT, UPDATE, DELETE` |
| `v_audit_scores` | 5 wymiarów CEFR | `SELECT, UPDATE` |
| `v_tasks` | taski per user | `SELECT, UPDATE(status)` |
| `v_testimonials` | katalog | `SELECT` |
| `v_pricing` | aktualny cennik | **`SELECT` only** |

Widoki są `UPDATABLE` przez `INSTEAD OF` triggery tam, gdzie potrzeba (bo widok z JOIN nie jest natywnie updatable).

---

## 3. Migracja legacy (Excel → Postgres)

**Zakres:** 1600 rekordów / 15 lat.

| Kolumna Excel | Cel | Uwagi |
|---|---|---|
| `ID` | `clients.id` | **zachowaj** — Przemek myśli tymi numerami; insert z explicit `id` (bigserial), potem `setval` na sekwencji |
| `Nazwa klienta` | `people.first_name/last_name` | split |
| `Organizacja` | `organizations.name` | NULL → B2C |
| `B2B / B2C` | `clients.type` | |
| `Handlowiec` | `clients.owner_user_id` | mapowanie po imieniu |
| `Branża` | `organizations.industry` | |
| `Źródło` | `clients.source` | mapowanie na enum |
| `Forma kontaktu` | `clients.contact_form` | |
| `Kwalifikacja leada` | `clients.qualification` | |
| `Data wpłynięcia` + `Godzina` | `clients.inbound_at` | **⚠️ serial Excela** (46149 = data, 0.4416 = godzina) |
| `Data szansy sprzedaży` … `Data utracenia` (11 kolumn) | **`opportunity_stage_history`** | każda data → wiersz z `to_stage` |
| `Etap` | `opportunities.stage` | |
| `Stan` | `opportunities.state` | |
| `Szansa sprzedaży Wartość` | `opportunities.value_pln` | |
| `Notatki` | `opportunities.notes` | |

**Pułapka:** daty w Excelu to **serial numbers** (46149 = dni od 1899-12-30), godzina to ułamek doby. Konwersja: `DATE '1899-12-30' + serial * INTERVAL '1 day'`.

**Kolejność:** `users` → `organizations` → `people` → `clients` → `opportunities` → `opportunity_stage_history`.

**Skrypt migracyjny:** jednorazowy, w Pythonie (`openpyxl` + `psycopg`), idempotentny (`ON CONFLICT (id) DO NOTHING`), z raportem rozbieżności.

---

## 4. crm-api — kontrakt

Bezstanowy. Bez bazy. Bez auth (sieć `internal`). ~200 linii.

| Endpoint | Metoda | Wejście | Wyjście |
|---|---|---|---|
| `/health` | GET | — | `{status, libreoffice_ok}` |
| `/render` | POST | `{payload, template_key}` | `{pptx: base64, pdf: base64, warnings: []}` |
| `/template/inspect` | POST | `{template_key}` | `{placeholders: [], slide_count, slide_map}` |

**Stack:** FastAPI + Pydantic v2 + `python-pptx` + LibreOffice (subprocess) + `boto3`/`minio` (pobranie szablonu).

**Flow `/render`:**
1. Pobierz `.potx` z MinIO (cache lokalny po `sha256`)
2. `python-pptx`: podmień placeholdery w runach
3. Usuń nieużywane slajdy celów / testimoniali
4. Zapisz `.pptx` do `/tmp`
5. `soffice --headless --convert-to pdf` (subprocess, timeout 60 s, unikalny `-env:UserInstallation`)
6. Zwróć oba jako base64 (albo strumień)

**Pułapki LibreOffice (obowiązkowe):**
- `-env:UserInstallation=file:///tmp/lo_$(uuid)` — osobny profil per wywołanie (race condition na `~/.config/libreoffice`)
- `timeout 60 soffice ...` — LO potrafi zawisnąć w nieskończoność
- Reap zombie procesów (`subprocess.run` z `timeout=`, potem `kill -9` grupy)
- **Serializacja** — max 1 konwersja naraz (wymuszona przez jeden konsument `job_queue`)

**Pułapka `python-pptx` — placeholdery w runach:**
PowerPoint dzieli tekst na `runs` przy **każdej zmianie formatowania**. `{{client_name}}` napisane w szablonie może fizycznie być trzema runami: `{{cli`, `ent_`, `name}}`. Naiwny `.replace()` **nie zadziała**.
→ Merge runów per paragraf przed podmianą, zachowując formatowanie pierwszego runa.

**Pułapka klonowania slajdów (cele 5–7):**
`python-pptx` **nie ma API** do kopiowania slajdu. Trzeba `copy.deepcopy` XML + re-attach relacji.
→ **To jest najbardziej ryzykowna linijka w projekcie. Testujesz ją w DNIU 1.**
→ **Plan B:** szablon zawiera 3 gotowe slajdy celów (max 6 celów), renderer **usuwa** nieużywane. Usuwanie jest trywialne i niezawodne. Tracisz elastyczność >6 celów — nikogo to nie obchodzi.

---

## 5. NocoDB — widok „Offer Builder" (to sprzedaje projekt)

**Zasada:** pola nazywają się **jak slajdy**, nie jak kolumny. Przemek otwiera i od razu widzi mapowanie.

| Pole NocoDB | Slajd | Typ | Uwagi |
|---|---|---|---|
| `Imię i nazwisko` | 1 | SingleLineText | |
| `Stanowisko` | 1 | SingleLineText | |
| `Data oferty` | 1 | Date | |
| `Poziom: Ogólny` | 3 | SingleSelect | `A1.0` … `C2.9` |
| `Poziom: Zakres języka` | 3 | SingleSelect | |
| `Poziom: Poprawność` | 3 | SingleSelect | |
| `Poziom: Płynność` | 3 | SingleSelect | |
| `Poziom: Komunikatywność` | 3 | SingleSelect | |
| `Opis sytuacji` | 3 | LongText | draft AI + korekta |
| `Nagłówek rekomendacji` | 4 | LongText | |
| `Wariant 1: produkt` | 4 | SingleSelect | z `pricing_tiers` |
| `Wariant 1: godziny` | 4 | SingleSelect | **tylko wartości z cennika** |
| `Wariant 1: cena` | 4 | **read-only** | ← trigger PG |
| `Wariant 2: warsztat` | 4 | SingleSelect | katalog + „brak" |
| `Wariant 2: godziny` | 4 | SingleSelect | |
| `Wariant 2: cena` | 4 | **read-only** | ← trigger PG |
| `Razem godzin` | 4 | **read-only** | ← trigger PG |
| `Razem cena` | 4 | **read-only** | ← trigger PG |
| `Cele szkoleniowe` | 5–7 | Linked Records | → `offer_goals` |
| `Testimoniale` | 12–24 | Linked Records (multi) | → `testimonials` |
| `Szablon` | — | Linked Record | → `offer_templates` |
| `Wersja` | — | read-only | |
| `Status generowania` | — | read-only | `queued`/`running`/`done`/`failed` |
| `⬇ PPTX` / `⬇ PDF` | — | URL | presigned MinIO |
| **`[Generuj ofertę]`** | — | **Button → webhook** | → n8n |

**Kluczowy efekt demo:** Przemek zmienia `60 → 45`, cena **przelicza się natychmiast** (trigger PG, NocoDB odświeża pole), klika Generuj, po ~20 s ma PPTX ze zmianą.

**Gotcha:** NocoDB Button webhook jest **fire-and-forget** — nie czeka na odpowiedź. Link nie pojawi się sam, dopóki n8n nie zrobi `PATCH` przez NocoDB API. Stąd pole `Status generowania` — Przemek widzi `generowanie…` → `gotowe`.

---

## 6. Workflowy n8n

### WF-1: Lead inbound
```
[Webhook: Cal.com booking.created]  LUB  [NocoDB: nowy wiersz w v_pipeline]
  → [Postgres] UPSERT people, clients, opportunities (stage='nowa')
  → [Postgres] INSERT tasks (assignee=Przemek, title='Zweryfikuj leada #{client_id}')
  → [Slack/email] notyfikacja
```

### WF-2: Po discovery call → task na transkrypcję
```
[Cal.com: booking.ended]  LUB  [Schedule: 30 min po scheduled_at]
  → [Postgres] INSERT discovery_calls
  → [Postgres] UPDATE opportunities SET stage='badanie_potrzeb'  (→ trigger loguje historię)
  → [Postgres] INSERT tasks ('Wklej / zatwierdź transkrypcję — {client}')
```

### WF-3: Transkrypcja → ekstrakcja AI
```
[NocoDB Button: 'Analizuj transkrypcję']  LUB  [Trigger: transcripts.curated_text IS NOT NULL]
  → [Postgres] INSERT job_queue (kind='ai_extract', priority=3)
  ─── (nocny scheduler LUB natychmiast, jeśli CPU wolne) ───
  → [Postgres] SELECT ... FOR UPDATE SKIP LOCKED
  → [HTTP] Anthropic API  (structured output, JSON Schema, prompt_version)
  → [Postgres] INSERT extractions (payload, model, prompt_version)
  → [Postgres] INSERT tasks ('Zatwierdź analizę AI — {client}', assignee=metodyk)
```
**Retry:** 3× z backoff. Po 3 failach → task „AI nie zadziałało, uzupełnij ręcznie".

### WF-4: Zatwierdzenie ekstrakcji → task audytu
```
[Trigger: extractions.accepted_at zmienione z NULL]
  → [Postgres] UPDATE organizations SET business_context = payload->'business_context'
  → [Postgres] INSERT participants (z payload)
  → [Postgres] INSERT audits (status='planned', auditor=Ola|Dorota)
  → [Postgres] INSERT tasks ('Przeprowadź audyt — {participant}')
```

### WF-5: Audyt → rekomendacja (draft AI)
```
[Trigger: audits.status → 'done']
  → [Postgres] SELECT audit + scores + extraction + client
  → [HTTP] Anthropic API → draft situation_description + goals
  → [Postgres] INSERT recommendations (approved_at = NULL)
  → [Postgres] INSERT recommendation_goals
  → [Postgres] INSERT tasks ('Zatwierdź rekomendację — {client}', assignee=metodyk+Przemek)
```

### WF-6: Generowanie oferty ⭐ (rdzeń MVP)
```
[NocoDB Button: 'Generuj ofertę']  → webhook  { record_id, table_id }
  │
  ├─ [Postgres] SELECT hydrated offer (offer + items + rec + goals + scores
  │              + testimonials + client + template)
  │
  ├─ [Postgres] INSERT offer_snapshots (status='queued', version=offers.version+1)
  ├─ [NocoDB API] PATCH record → Status generowania = 'generowanie…'
  │
  ├─ [Postgres] INSERT job_queue (kind='render_offer', priority=10)   ← NAJWYŻSZY
  │
  ├─ [HTTP] crm-api POST /render  { payload, template_key }
  │         (timeout 90 s, retry 2×)
  │
  ├─ [MinIO] PUT offers/{client_id}/v{n}.pptx
  ├─ [MinIO] PUT offers/{client_id}/v{n}.pdf
  │
  ├─ [Postgres] UPDATE offer_snapshots
  │             SET status='done', minio_key, sha256, payload_snapshot = <hydrated JSON>
  ├─ [Postgres] UPDATE offers SET version = version + 1
  ├─ [Postgres] UPDATE opportunities SET stage='przygotowanie_oferty'
  │
  └─ [NocoDB API] PATCH record → Status='gotowe', ⬇PPTX = presigned URL, ⬇PDF = presigned URL
```
**Error branch:** `UPDATE offer_snapshots SET status='failed', error=...` + `PATCH NocoDB → 'BŁĄD'` + task dla Ciebie.

### WF-7: Upload szablonu (`.potx`)
```
[NocoDB: nowy wiersz w offer_templates z załącznikiem]
  → [MinIO] PUT templates/{name}_v{n}.potx
  → [HTTP] crm-api POST /template/inspect
  → [Postgres] UPDATE offer_templates SET placeholder_manifest, slide_map
  → [IF] brakuje wymaganych placeholderów
       → [NocoDB] PATCH → Status = 'BŁĄD: brakuje {{cefr_overall}}'
     [ELSE]
       → SET active = true
```

### WF-8: Scheduler nocny
```
[Cron 02:00]  → przetwórz job_queue WHERE priority <= 3   (AI, batch)
[Cron 03:00]  → backup: pg_dump → MinIO; mongodump → MinIO
[Cron 03:30]  → MinIO → offsite (rclone → S3/Backblaze)
[Cron 04:00 nd] → VACUUM ANALYZE; REINDEX
```

**To jest Twój „tryb nocny"** — deklaratywnie, bez `docker compose down`, bez Docker socketa w n8n.

---

## 7. Priorytetyzacja CPU (prawdziwe wąskie gardło)

**RAM masz z zapasem (3.2 GB). CPU nie — masz 2 vCPU.**

LibreOffice = 1 pełny rdzeń przez 5–10 s. Jeśli Przemek generuje ofertę **na żywo przy kliencie**, a n8n akurat mieli AI-ekstrakcję → render czeka, Postgres zagłodzony, NocoDB muli. **Przemek stoi przed klientem i patrzy w spinner.**

### Rozwiązanie (3 warstwy, zero nowych narzędzi)

**1. Priorytety w `job_queue`**

| Zadanie | Priorytet |
|---|---|
| Render oferty (klik) | **10** |
| Regeneracja po zmianie danych | 5 |
| AI-ekstrakcja | 3 |
| Backup, ASR, cleanup | 1 |

Jeden konsument, `ORDER BY priority DESC` → render zawsze wyprzedza AI.

**2. `cpu_shares` w compose** (soft priority, działa tylko przy kontencji)

| Serwis | `cpu_shares` |
|---|---|
| `postgres` | **2048** (nigdy nie głoduje) |
| `n8n` | 1024 |
| `nocodb` | 1024 |
| `crm-api` | **512** (ustępuje bazie) |
| `librechat` | 512 |

**3. Okna czasowe** — ciężkie joby na 02:00–04:00 (WF-8).

### Czego NIE robić
❌ `docker compose down` z n8n w ciągu dnia:
- wymaga Docker socketa w n8n → **root na hoście**
- restart Postgresa = cold cache → wolne zapytania przez minuty
- Uptime Kuma zaczyna alertować

**Zysk: 1 GB RAM, którego nie potrzebujesz. Koszt: dziura bezpieczeństwa.** Nie warto.

---

## 8. Wąskie gardła i pułapki

### 8.1 PgBouncer + n8n — prepared statements ⚠️
PgBouncer w **transaction mode** nie obsługuje protokołu prepared statements. n8n (node-postgres) i NocoDB mogą ich używać.

**Objaw:** losowe `prepared statement "S_1" already exists`.

**Rozwiązanie:**
- PgBouncer ≥ 1.21 + `max_prepared_statements = 100` (od tej wersji PgBouncer to obsługuje w transaction mode)
- Albo: n8n/NocoDB → **bezpośrednio do Postgresa** (`5432`), tylko `crm-api` przez PgBouncer
- **Ustawienia:** `pool_mode=transaction`, `default_pool_size=20`, `max_client_conn=100`, `server_lifetime=600`

### 8.2 NocoDB schema drift ⚠️⚠️
NocoDB podpięty do zewnętrznego Postgresa **potrafi zmodyfikować schemat** przy „Sync" — dodać kolumny meta (`nc_order`), zmienić typy.

**Rozwiązanie:**
- Osobny user `nocodb_app` z `GRANT SELECT, INSERT, UPDATE, DELETE` **tylko na widokach**
- **`REVOKE CREATE ON SCHEMA public FROM nocodb_app`** ← krytyczne
- `REVOKE ALL ON ALL TABLES` → grant tylko na `v_*`
- NocoDB nigdy nie widzi tabel bazowych

### 8.3 Rate limity API AI
Anthropic/OpenAI mają limity RPM/TPM. Transkrypt 40-min ≈ 8–12k tokenów.

**Rozwiązanie:** kolejka (`priority=3`), retry z exponential backoff (3×), circuit breaker → po 3 failach task manualny. Przy 5 leadach/dzień to nieistotne, ale nie zakładaj że zawsze zadziała.

### 8.4 Backup — pułapka self-hostingu ⚠️⚠️⚠️
**3 osobne systemy stanu:** Postgres, MinIO, MongoDB. Backup jednego bez pozostałych = bezużyteczny.

| Co | Jak | Retencja | Gdzie |
|---|---|---|---|
| **Postgres** | `pg_dump -Fc` (nocnie) + WAL archiving (opcjonalnie) | 30 dni | MinIO + offsite |
| **MinIO** | `mc mirror` → offsite (Backblaze B2 / Hetzner Storage Box) | 90 dni | offsite |
| **MongoDB** | `mongodump` | 14 dni (tylko LibreChat, mniej krytyczne) | MinIO + offsite |
| **n8n workflows** | Export JSON → Git (**n8n ma natywny Git sync**) | ∞ | Git |
| **Schema PG** | Migracje w Git | ∞ | Git |
| **NocoDB meta** | Meta w tym samym PG → objęte `pg_dump` | — | — |

> **⚠️ Backup MinIO do MinIO to nie backup.** Musi być offsite. 80 GB NVMe — jak dysk padnie, tracisz wszystko.

**Restore drill: obowiązkowy przed oddaniem klientowi.** Odtwórz całość na czystym VPS z samych backupów. Jeśli nie przećwiczysz — nie masz backupu, masz nadzieję.

### 8.5 MinIO versioning + lifecycle

| Bucket | Versioning | Lifecycle |
|---|---|---|
| `offers` | **ON** | Retencja ∞ (snapshoty ofert = dokumenty handlowe) |
| `templates` | **ON** | Retencja ∞ |
| `recordings` | OFF | **Expire po 90 dniach** (⚠️ 80 GB dysku!) |
| `transcripts` | OFF | ∞ (tekst, mały) |
| `backups` | OFF | Expire 30 dni |

**Dysk 80 GB — realne zagrożenie:** nagrania to ~50 MB/h. Przy 20 spotkaniach/mies. = 1 GB/mies. Przez rok = 12 GB. **Do przyjęcia, ale monitoruj** (Uptime Kuma → alert przy 80% dysku).

### 8.6 Whisper / ASR — NIE na tym VPS ❌
Rozważałeś nocne przetwarzanie. Matematyka:
- `whisper.cpp` model `small`, CPU-only, 2 vCPU → **~1.5–2× realtime**
- 40-min rozmowa = **60–80 min mielenia CPU**
- Jakość dla mieszanego PL/EN → **słaba** (patrz transkrypt 1639 — sieczka)

**Rekomendacja:** zewnętrzny ASR (Deepgram / AssemblyAI / OpenAI Whisper API). Koszt ~$0.006/min → 40-min rozmowa = **$0.24**. Kilkanaście rozmów/mies. = **~$4**.

Nie warto poświęcać VPS-a i jakości dla $4/mies. **Nagranie → MinIO → n8n → zewnętrzny ASR → transkrypt do PG.**

### 8.7 Ready-to-migrate (wymóg klienta)

| Zasada | Realizacja |
|---|---|
| Zero credentiali w `docker-compose.yml` | **Wszystko przez `${VAR}` z `.env`** |
| LibreChat ↔ Mongo tylko przez `${MONGO_URI}` | ✅ |
| Odpięcie kontenera Mongo nie wysypuje LibreChata | ✅ — zmiana `MONGO_URI` na zewnętrzny host |
| To samo dla Uptime Kuma | Kuma = SaaS-ready (Uptime Kuma Cloud / Better Uptime) |

**Analogicznie przygotuj:** `${POSTGRES_URI}`, `${MINIO_ENDPOINT}`, `${S3_*}` — żeby dało się wyprowadzić bazę i storage do managed service bez zmiany compose'a.

**`.env` — pełna lista (do wygenerowania przy bootstrapie):**
```
POSTGRES_HOST / PORT / DB / USER / PASSWORD
POSTGRES_URI            (composed)
PGBOUNCER_*
NOCODB_DB_USER / PASSWORD   (ograniczony!)
MONGO_URI               ← LibreChat, ready-to-migrate
MINIO_ROOT_USER / PASSWORD / ENDPOINT
MINIO_BUCKET_*
N8N_ENCRYPTION_KEY      ← ⚠️ utrata = utrata wszystkich credentiali w n8n
N8N_WEBHOOK_URL
CRM_API_URL             (internal)
ANTHROPIC_API_KEY
ASR_API_KEY
CADDY_DOMAIN / EMAIL
BACKUP_S3_*             (offsite)
```

> **`N8N_ENCRYPTION_KEY` — zapisz w password managerze klienta.** Utrata = utrata wszystkich credentiali zapisanych w n8n.

### 8.8 Cal.com
**Rekomendacja: Cal.com Cloud** (free tier wystarcza dla 1 handlowca).
- ✅ Natywny webhook → n8n (`booking.created`, `booking.ended`)
- ✅ Zero Azure AD, zero app registration, zero Graph API
- ✅ **Zero RAM na VPS** (self-hosted to +600 MB + własna baza)

### 8.9 Ryzyko #1 projektu — nie techniczne ⚠️⚠️⚠️
Dokument klienta przyznaje wprost:
> *„Które elementy rekomendacji są oparte na kryteriach metodycznych, które trzeba spisać, bo obecnie funkcjonują głównie »w głowie«."*

**Skąd `B2.6` vs `B2`? Dlaczego 1638 → 60h BE + 15h warsztat, a 1639 → 60h English for IT?**

Ten mapping **jest produktem.** Bez niego zbudujesz system, który generuje puste slajdy.
**n8n tego nie rozwiąże. Ustalone: wyciągacie to iteracyjnie po MVP.** Do MVP: metodyk wpisuje ręcznie, AI tylko draftuje tekst.

---

## 9. Kolejność wdrożenia

### FAZA 0 — Bramka techniczna (DZIEŃ 1) ⚠️
**Zanim zbudujesz cokolwiek innego.**

1. Wyciągnij szablon z decku 1638 → `coaction_b2c_v1.potx`
2. Zaznacz placeholdery na slajdach 1, 3, 4, 5–7
3. Napisz minimalny `render_offer.py` (hardcoded JSON → PPTX)
4. **TEST:** czy podmiana tekstu w runach działa na tym 11 MB decku?
5. **TEST:** czy klonowanie / usuwanie slajdów celów działa?
6. **TEST:** czy `soffice --convert-to pdf` daje poprawny PDF?

> **To jest jedyny prawdziwy risk techniczny.** Jeśli tu się wywali → Plan B (3 gotowe slajdy celów, tylko usuwanie).
> **Nie idź dalej, dopóki to nie działa.**

### FAZA 1 — Infrastruktura (dni 2–3)
1. VPS: `ufw` (tylko 22, 80, 443), fail2ban, unattended-upgrades
2. Docker + Compose v2
3. `.env` (wygeneruj hasła: `openssl rand -base64 32`)
4. Sieci: `edge`, `internal`, `data`, `mongo`
5. **Postgres** (bind `127.0.0.1`, `shared_buffers=1GB`, `work_mem=16MB`, `max_connections=100`)
6. **PgBouncer** (`transaction`, `max_prepared_statements=100`)
7. **Caddy** + domeny (`back-office.`, `n8n.`, `chat.`, `s3.`, `status.`)
8. **MinIO** + buckety + versioning + lifecycle
9. **Uptime Kuma** — monitoring wszystkiego od razu

### FAZA 2 — Baza (dni 4–5)
1. Migracje (`dbmate` / `Atlas`) w Git
2. Enumy → tabele → indeksy → triggery
3. **Trigger cenowy** (`offer_items` → `offers`)
4. **Trigger historii** (`opportunities.stage` → `opportunity_stage_history`)
5. Seed: `pricing_tiers` (ze slajdu 8), `testimonials` (slajdy 12–24), `users`
6. Widoki `v_*` + `INSTEAD OF` triggery
7. `nocodb_app` user + `GRANT` + **`REVOKE CREATE ON SCHEMA public`**
8. **Migracja legacy Excela** (1600 rekordów)

### FAZA 3 — crm-api (dni 6–7)
1. FastAPI + Pydantic + `python-pptx` + LibreOffice (Dockerfile)
2. `POST /render` (z Fazy 0)
3. `POST /template/inspect`
4. Pobieranie szablonu z MinIO + cache po `sha256`
5. Timeout, unikalny profil LO, reap zombie
6. **Nie wystawiaj przez Caddy** — tylko sieć `internal`

### FAZA 4 — n8n + NocoDB (dni 8–10)
1. n8n: credentials (PG, MinIO, Anthropic, NocoDB), **Git sync** workflowów
2. **WF-6 (generowanie oferty) — najpierw!** To jest demo.
3. NocoDB: podłącz do widoków, zbuduj **Offer Builder** (§5)
4. Button field → webhook n8n
5. Pola po polsku, ukryj techniczne kolumny, grupowanie
6. **Test pętli:** zmień 60h → 45h → Generuj → PPTX ze zmianą

### FAZA 5 — DEMO (dzień 11) 🎯
**Przemek klika, nie Ty.**
1. Otwiera rekord 1638 w NocoDB
2. Zmienia `60h → 45h` → **cena przelicza się na jego oczach**
3. Zmienia testimoniale (IT → HR)
4. Klika `[Generuj ofertę]`
5. Po ~20 s ma PPTX. **Swój deck. Ze swoją zmianą.**

**Jeśli to zadziała — kupi.**

### FAZA 6 — Reszta pipeline'u (dni 12–18)
WF-1 … WF-5, WF-7, WF-8. Taski. AI-ekstrakcja. Cal.com.

### FAZA 7 — Hardening + przekazanie (dni 19–21)
1. Backup + **restore drill na czystym VPS**
2. Uptime Kuma: wszystkie serwisy + dysk + cert expiry
3. `cpu_shares`
4. Dokumentacja (runbook: restart, restore, dodanie pola, zmiana szablonu)
5. **Szkolenie klienta:** NocoDB (codziennie), n8n (rozszerzanie), upload szablonu

---

## 10. Dług techniczny — świadomy

| Dług | Kiedy zapłacić |
|---|---|
| **Brak live preview oferty** — Przemek czeka 20 s na każdą iterację | Gdy zaboli → **Appsmith Cloud** albo własny front (FastAPI + HTMX) |
| **NocoDB nie waliduje biznesu** — broni tylko baza (CHECK/FK) | OK na zawsze, jeśli constrainty są szczelne |
| **Kryteria metodyczne „w głowie"** | Iteracyjnie po MVP — to jest wspólna praca z metodykami |
| **ASR zewnętrzny** (nie self-hosted) | Nigdy — $4/mies. to nie jest problem |
| **Brak modułu post-sprzedażowego** (lektorzy, analiza lekcji) | Wersja 2.0 + większy dysk |

---

## 11. Otwarte pytania (do potwierdzenia z klientem)

1. **Czy Przemek zaakceptuje, że NIE edytuje PPTX ręcznie?** Jeśli nie → +3–4 dni na re-import tabeli „Podsumowanie handlowe" (Model 3).
2. ~~**Domena**~~ — **rozstrzygnięte:** `back-office.coaction.pl` (zaakceptowane przez CEO). CRM to część backoffice; docelowo pod tą samą domeną znajdą się też widoki dla lektorów (np. notatki po lekcji).
3. **Kto dostaje taski** — potwierdzić listę: Przemek (sprzedaż), Ola/Dorota (metodyka), Kasia (?), Paulina (finanse).
4. **Offsite backup** — gdzie? (Backblaze B2 ~$6/TB/mies., Hetzner Storage Box ~€3/mies. za 1 TB)
5. **Dostawca ASR** — Deepgram / AssemblyAI / OpenAI Whisper API?