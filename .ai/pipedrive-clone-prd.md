# PRD: CoAction CRM (MVP)

> Implementation target: Claude Code agent.
> Status: ready for implementation, with open questions listed in section 13. **Do not invent answers to open questions. Stop and ask the owner.**

---

## 1. Context

**CoAction** (coaction.pl) is a Warsaw-based business English school. It specializes in English for IT and business, and its offer includes 1:1 and group courses, English+Skills workshops, and language audits. It sells both B2B (companies buying training for employees, usually via HR or the CEO) and B2C (individuals). Most B2B growth comes from referrals.

**Current state:** for the last ~3 years the team has worked on an Excel file on SharePoint (`old-crm.xls`). They used Pipedrive long ago, but it was too expensive, they used only a fraction of its features, and its template did not fit their process.

**Team:** 1 salesperson, plus methodologists and trainers who run audits.

**Owner goal (secondary but explicit):** the system owner builds this to learn customer acquisition processes in depth. The data model must make acquisition metrics measurable: source attribution, stage velocity, audit-to-course conversion, and retention vs. new business revenue.

---

## 2. Goals and non-goals

### Goals (MVP)
1. Single source of truth for people (`contacts`) and companies, with deduplication by email.
2. Lead intake from web forms and cal.com, plus lead qualification (MQL → SQL).
3. Opportunity pipeline with stage history, typed opportunities (new business, continuation, win-back, upsell), and multi-line offers (audits plus courses in one offer).
4. B2B participant tracking (e.g. 15 employees, each audited, 10 enrolled).
5. Assessments (audit results and other level assessments) stored per person.
6. Task boards per team member (e.g. a kanban view for Dorota).
7. One-time import of `old-crm.xls` with stage history reconstruction.
8. Reporting SQL views for acquisition metrics.
9. GDPR basics: consents, retention tracking.

### Non-goals (MVP)
- Lesson scheduling and trainer management after the sale (delivery system).
- Invoicing.
- Email inbox sync.
- Marketing campaign management, full UTM attribution, tags (Phase 2).
- AI agents (Phase 2), except where noted.
- Multi-tenancy, custom roles and permissions (NocoDB handles UI access).

---

## 3. Stack

| Component | Role |
|---|---|
| PostgreSQL (self-hosted VPS) | System of record |
| NocoDB | UI for the team (grid, kanban, forms) and **primary write API** for n8n |
| n8n | Automations and integrations |
| cal.com | Meeting booking (replacing MS Bookings) |
| LibreChat + OpenRouter | AI agents (Phase 2) |

---

## 4. Architecture decisions (binding)

**AD-1. The schema is owned by SQL migrations.** Never create or alter tables from the NocoDB UI. After every migration, run "Sync metadata" in NocoDB. NocoDB's Postgres data reflection does not automatically pick up external DDL changes.
- Recommended tool: `dbmate` (plain SQL up/down files). **Confirm with the owner before choosing** (open question Q10).
- Before the first schema change after go-live, verify on a copy that migration plus metadata sync **preserves NocoDB table and field IDs**. n8n workflows reference them.

**AD-2. Writes go through the NocoDB API. Analytical reads go through SQL.**
- n8n writes records via the NocoDB REST API (audited, and the UI refreshes in real time).
- Reporting and agents read via a dedicated **read-only Postgres role** (`crm_readonly`) against the SQL views in section 9.
- Exception: the bulk import (section 11) writes directly via SQL inside a transaction.

**AD-3. Business-critical history is enforced by database triggers**, independent of the write path (API, SQL, import). This applies to `opportunity_stage_history`, `updated_at`, `contacts.last_activity_at` and `contacts.lifecycle_stage`.

**AD-4. Idempotency over transactions.** The NocoDB API has no multi-table transactions, so every n8n workflow must be safe to rerun:
- Look up before creating (contact by email, opportunity by `source_lead_id`).
- Unique constraints in the DB act as the last line of defence (see the constraints below).
- Every n8n workflow has an error workflow that logs failures and creates a task for the salesperson.

**AD-5. Webhook loop protection.** Workflows triggered by NocoDB webhooks must:
- act only when the specific triggering field actually changed to the target value, and
- check whether the side effect already exists (e.g. an opportunity with this `source_lead_id`) before creating it.

**AD-6. People data lives only in `contacts`.** Role tables (`leads`, `participants`, `meeting_attendees`, `opportunity_contacts`) hold `contact_id` and role-specific fields, never names, emails or phones. NocoDB views on role tables show people data via lookup fields.

**AD-7. Opportunities belong to contacts and companies, not to leads.** A lead is a one-time funnel entry. `opportunities.source_lead_id` is set only on the opportunity created from that lead, for attribution. Continuations, upsells and win-backs have `source_lead_id = NULL`.

**AD-8. Opportunity `type` is computed by a deterministic rule (section 8.3), never by an LLM.** An LLM may only detect intent (e.g. "client wants more").

**AD-9. Team members are a real table (`team_members`)**, not the NocoDB User field, so SQL views and agents can join on people.

**AD-10. Lists that the business edits are lookup tables** (stages, sources, reasons, products). Fixed system values (e.g. `opportunities.type`) are `text` columns with a `CHECK` constraint.
- **Verify on the test instance** how NocoDB renders a `text` column with a `CHECK` constraint, and configure it as SingleSelect in NocoDB if needed. Do not use native Postgres `ENUM` types unless the test shows NocoDB handles them better. Report the finding to the owner.

---

## 5. Conventions

- Table names: plural `snake_case`, English. Columns: `snake_case`, English.
- Primary key: `id bigint generated always as identity`.
- Every table has `created_at timestamptz not null default now()` and `updated_at timestamptz not null default now()`, plus an `updated_at` trigger.
- All timestamps are `timestamptz`. Business timezone: `Europe/Warsaw`.
- Money: `numeric(12,2)` plus `currency char(3) default 'PLN'`.
- Foreign keys: `on delete restrict` by default. Join tables use `on delete cascade`.
- Every table that receives imported data has `legacy_id text null` and `import_source text null`, with a unique index on `(import_source, legacy_id)` where `legacy_id` is not null.
- All code, SQL, comments and n8n node names are in English.

---

## 6. Data model

Notation: `column type [constraints] — note`. `FK→table` means a foreign key to `table.id`.

### 6.1 People and companies

#### `team_members`
```
full_name        text not null
email            text not null unique
role             text not null check in ('sales','methodologist','trainer','admin')
is_active        boolean not null default true
```

#### `companies`
```
name             text not null
industry         text null
website          text null
sharepoint_url   text null            — client folder from legacy Excel
notes            text null
archived_at      timestamptz null
legacy_id, import_source
```
Index: `lower(name)` (non-unique; dedupe during import, see 11.4).

#### `contacts`
```
first_name       text null
last_name        text null
email            citext null          — primary dedupe key
phone            text null
linkedin_url     text null
industry         text null            — relevant for B2C individuals
sharepoint_url   text null
lifecycle_stage  text not null default 'subscriber'
                 check in ('subscriber','lead','customer','former_customer')
                 — maintained by DB logic only (8.6); read-only in NocoDB
last_activity_at timestamptz null     — maintained by triggers (8.7)
anonymized_at    timestamptz null     — GDPR retention (8.8)
notes            text null
legacy_id, import_source
```
Constraints: `unique (email) where email is not null`. Requires the `citext` extension.

#### `company_contacts` — employment history (key for referral/job-change tracking)
```
company_id       FK→companies not null
contact_id       FK→contacts not null
job_title        text null
started_at       date null
ended_at         date null            — null = current
is_primary       boolean not null default false
```
Constraint: at most one row per `(company_id, contact_id)` with `ended_at is null`.

### 6.2 Funnel

#### `lead_sources` (lookup) — where the person found CoAction
```
name             text not null unique — e.g. Google, Referral, LinkedIn, Newsletter, Legacy
is_active        boolean not null default true
```
Seed: values found in the legacy `Źródło` column, plus `Referral` and `Legacy`.

#### `lead_magnets` (lookup) — what the person signed up for
```
name             text not null unique
kind             text not null check in ('trial_lesson','ebook','webinar','audit','contact_form','other')
url              text null
is_active        boolean not null default true
```

#### `form_submissions` — raw intake, never edited
```
received_at      timestamptz not null
channel          text not null check in ('website_form','cal_com','ms_bookings','email','phone','manual','import')
lead_magnet_id   FK→lead_magnets null
contact_id       FK→contacts null     — set after matching
payload          jsonb not null       — raw data as received
utm_source, utm_medium, utm_campaign  text null
```

#### `disqualification_reasons` (lookup)
```
name             text not null unique
is_active        boolean not null default true
```

#### `leads`
```
contact_id               FK→contacts not null
form_submission_id       FK→form_submissions null
lead_source_id           FK→lead_sources null
lead_magnet_id           FK→lead_magnets null
segment                  text not null check in ('b2b','b2c')
contact_method           text null check in ('website_form','cal_com','ms_bookings','email','phone','referral','other')
received_at              timestamptz not null
qualification_status     text not null default 'new'
                         check in ('new','mql','sql','disqualified')
qualified_at             timestamptz null       — set when status becomes 'sql'
disqualification_reason_id FK→disqualification_reasons null
owner_id                 FK→team_members null
referral_id              FK→referrals null
legacy_id, import_source
```
Rules: `disqualification_reason_id` is required when status = `disqualified` (CHECK constraint).

#### `referrals`
```
referrer_contact_id  FK→contacts not null   — who recommended
referred_contact_id  FK→contacts null
referred_company_id  FK→companies null
referred_at          date not null
notes                text null
```
Constraint: at least one of `referred_contact_id` / `referred_company_id` is not null.

### 6.3 Sales

#### `pipelines`
```
name             text not null unique
is_default       boolean not null default false
```
Seed: one pipeline named `Sales` (default).

#### `pipeline_stages`
```
pipeline_id      FK→pipelines not null
key              text not null          — stable machine key
name             text not null          — display name (Polish allowed)
position         int not null
outcome          text not null default 'open' check in ('open','won','lost')
```
Unique: `(pipeline_id, key)`, `(pipeline_id, position)`.

Seed (confirmed with the owner):

| position | key | name | outcome | legacy Excel date column |
|---|---|---|---|---|
| 1 | new | Nowa | open | `Data szansy sprzedaży` |
| 2 | needs_analysis | Badanie potrzeb | open | `Data badania potrzeb` |
| 3 | demo | Prezentacja propozycji (DEMO) | open | `Data DEMO` |
| 4 | proposal_sent | Oferta wysłana | open | `Data wysłania oferty` |
| 5 | proposal_review | Omówienie oferty | open | `Data omówienia oferty` |
| 6 | contract_sent | Umowa wysłana | open | `Data wysłania umowy` |
| 7 | won | Umowa podpisana | won | `Data podpisania umowy` |
| 8 | lost | Utracona | lost | `Data utracenia` |

DEMO is a presentation of the proposal **before** the formal offer.

#### `products` (lookup)
```
name             text not null unique
kind             text not null check in ('course_1on1','course_group','workshop','audit','other')
default_price    numeric(12,2) null
currency         char(3) not null default 'PLN'
is_active        boolean not null default true
```

#### `lost_reasons` (lookup)
```
name             text not null unique
is_active        boolean not null default true
```

#### `opportunities` — one opportunity = one offer
```
name                 text not null
contact_id           FK→contacts not null    — B2C buyer or main B2B contact
company_id           FK→companies null       — set for B2B
segment              text not null check in ('b2b','b2c')
type                 text not null check in ('new_business','continuation','win_back','upsell','unknown')
                     — computed by rule 8.3; 'unknown' only for legacy rows
pipeline_id          FK→pipelines not null
stage_id             FK→pipeline_stages not null
owner_id             FK→team_members null
source_lead_id       FK→leads null unique    — only for the opportunity created from a lead (AD-7)
payer                text not null default 'contact' check in ('contact','company')
                     — who pays; independent of who learns (see Q3)
amount               numeric(12,2) null      — total offer value
currency             char(3) not null default 'PLN'
expected_close_date  date null
won_at               timestamptz null
lost_at              timestamptz null
lost_reason_id       FK→lost_reasons null
service_start_date   date null
service_end_date     date null               — REQUIRED when won; drives rule 8.3
archived_at          timestamptz null
notes                text null
legacy_id, import_source
```
Rules:
- `won_at` / `lost_at` are set automatically when the stage outcome changes (trigger).
- Opportunity is "won" if the stage outcome is `won`. The salesperson moves it to won when at least one line is won.
- `service_end_date` must be set when the stage outcome is `won`. Enforce this via an n8n/NocoDB validation and a nightly data-quality check, **not** a hard DB constraint (legacy rows lack it).

#### `opportunity_products` — offer lines with their own outcome
```
opportunity_id       FK→opportunities not null (cascade)
product_id           FK→products not null
quantity_proposed    int not null default 1 check > 0
quantity_won         int null check >= 0 and <= quantity_proposed
unit_price           numeric(12,2) null
status               text not null default 'proposed' check in ('proposed','won','lost')
lost_reason_id       FK→lost_reasons null
notes                text null
```
Covers: audits only (audit line `won`, course line `lost`) and partial uptake (`quantity_proposed=15`, `quantity_won=10`).

#### `opportunity_contacts` — people involved on the buyer side
```
opportunity_id   FK→opportunities not null (cascade)
contact_id       FK→contacts not null
role             text not null check in ('decision_maker','buyer','champion','influencer','other')
```
Unique: `(opportunity_id, contact_id, role)`.

#### `opportunity_stage_history` — written by trigger only
```
opportunity_id   FK→opportunities not null (cascade)
from_stage_id    FK→pipeline_stages null
to_stage_id      FK→pipeline_stages not null
changed_at       timestamptz not null default now()
changed_by       text null              — 'nocodb', 'n8n', 'import', or user email if available
```
Read-only in NocoDB.

### 6.4 Delivery-related (scope limited to sales needs)

#### `participants` — one row per person per opportunity
```
opportunity_id           FK→opportunities not null
opportunity_product_id   FK→opportunity_products null   — which line they enrolled in
contact_id               FK→contacts not null
status                   text not null default 'candidate'
                         check in ('candidate','audit_scheduled','audited','enrolled','not_enrolled')
notes                    text null
```
Unique: `(opportunity_id, contact_id)`.

#### `assessments`
```
contact_id       FK→contacts not null       — result follows the person across companies
participant_id   FK→participants null       — opportunity context, if any
meeting_id       FK→meetings null
assessor_id      FK→team_members null
assessment_type  text not null check in ('audit','placement','progress','final')
                 — the owner's "single select type" (confirm values, Q6)
conducted_at     timestamptz null
billable         boolean not null default false
report_url       text null
-- 5 short text fields + 3 long text fields: NAMES TBD (Q6)
```
**Blocking:** the owner specified 5 `text` (short) and 3 long-text result fields but has not named them. Ask for the names before writing this migration. Do not use placeholder names like `field_1`.

### 6.5 Work and meetings

#### `meetings` — synced from cal.com (the owner already tests this sync; integrate, don't rebuild)
```
external_source  text not null check in ('cal_com','ms_bookings','manual')
external_id      text null
title            text not null
meeting_kind     text not null check in ('trial_lesson','needs_analysis','demo','proposal_review','audit','other')
starts_at        timestamptz not null
ends_at          timestamptz null
status           text not null default 'scheduled' check in ('scheduled','completed','cancelled','no_show')
organizer_id     FK→team_members null
opportunity_id   FK→opportunities null
meeting_url      text null
notes            text null
```
Unique: `(external_source, external_id)` where `external_id` is not null.
**Before implementing, inspect the owner's existing `meeting` table and cal.com sync workflow** and adapt (rename to `meetings`, add columns) instead of replacing them. Ask if anything conflicts.

#### `meeting_attendees`
```
meeting_id       FK→meetings not null (cascade)
contact_id       FK→contacts not null
attendance       text null check in ('attended','no_show')
```
Unique: `(meeting_id, contact_id)`.

#### `tasks` — the work layer (kanban boards)
```
title            text not null
description      text null
assignee_id      FK→team_members null
status           text not null default 'todo' check in ('todo','in_progress','done','cancelled')
due_at           timestamptz null
completed_at     timestamptz null
contact_id       FK→contacts null
company_id       FK→companies null
opportunity_id   FK→opportunities null
participant_id   FK→participants null
assessment_id    FK→assessments null
created_by       text null            — 'n8n:<workflow>' or user
```
NocoDB view: "Dorota Board" = Kanban grouped by `status`, filter `assignee = Dorota`. Create one such view per active team member.

#### `activities` — notes, calls, emails (log)
```
activity_type    text not null check in ('note','call','email','other')
occurred_at      timestamptz not null default now()
author_id        FK→team_members null
contact_id       FK→contacts null
company_id       FK→companies null
opportunity_id   FK→opportunities null
subject          text null
body             text null
legacy_id, import_source
```
Constraint: at least one of `contact_id`, `company_id`, `opportunity_id` is not null.

### 6.6 Compliance and system

#### `consents`
```
contact_id       FK→contacts not null
purpose          text not null check in ('newsletter','marketing','data_processing')
granted          boolean not null
granted_at       timestamptz not null
withdrawn_at     timestamptz null
source           text not null        — e.g. 'ebook_form', 'website_form', 'import'
evidence         jsonb null           — form payload, IP, consent text version
```

#### `app_settings`
```
key              text primary key
value            text not null
description      text null
```
Seed: `continuation_threshold_days` (value **TBD**, Q1; do not seed a guess, leave the workflow failing loudly until set), `retention_years = 5`.

#### `import_issues`
```
import_source    text not null
legacy_id        text null
severity         text not null check in ('warning','error')
issue            text not null
raw_row          jsonb null
resolved_at      timestamptz null
```

---

## 7. NocoDB setup

- Connect Postgres as an external data source. Use one dedicated DB role for NocoDB with DML rights (no DDL).
- Mark read-only (in NocoDB field settings) the fields `contacts.lifecycle_stage`, `contacts.last_activity_at`, all of `opportunity_stage_history`, `form_submissions.payload`, `won_at`, `lost_at`.
- Views to create:
  - **Leads – to qualify**: `leads` where status in (new, mql), lookup to contact name/email, sorted by `received_at`.
  - **Pipeline**: `opportunities` kanban by `stage_id`, excluding archived.
  - **Participants – <company>**: `participants` grid filtered by opportunity, lookups to the contact.
  - **<Name> Board**: `tasks` kanban per team member.
  - **Renewals – next 30 days**: `opportunities` won with `service_end_date` within 30 days.
- Webhooks are used by the n8n workflows in section 8. Document every webhook (table, event, target workflow) in `docs/webhooks.md`.

---

## 8. Automations (n8n) and DB logic

Each workflow is a separate n8n workflow, exported as JSON to the repo under `n8n/`.

### 8.1 WF-01 Intake (form / cal.com trial lesson)
Trigger: website form webhook or cal.com booking (trial lesson event type).
1. Insert `form_submissions` with the raw payload.
2. Match the contact by email (case-insensitive). If not found, create a contact.
3. If the form says "for my company", find or create `companies` (by name, case-insensitive) and `company_contacts`. Set `segment = 'b2b'`. Otherwise `segment = 'b2c'`.
4. Create `leads` (status `new`, source, magnet, method).
5. If a consent checkbox is present, insert `consents`.
6. Create a task for the salesperson: "Qualify lead: <name>".

The form tool and field names are TBD (Q7).

### 8.2 WF-02 Lead → SQL conversion
Trigger: NocoDB webhook "after update" on `leads`.
Guard (AD-5): proceed only if `qualification_status = 'sql'` **and** no opportunity exists with `source_lead_id = lead.id`.
1. Set `leads.qualified_at = now()` if null.
2. Compute the opportunity type via rule 8.3.
3. Create `opportunities`: stage `new`, `source_lead_id = lead.id`, `contact_id`, `company_id` (if b2b), `segment`, `owner_id = lead.owner_id`, name `"<Company or Contact> – <date>"`.
4. Create a task: "Schedule needs analysis with <name>".

The unique constraint on `source_lead_id` protects against duplicates if the guard races.

### 8.3 Opportunity type rule (deterministic)
Implement as a SQL function `compute_opportunity_type(contact_id bigint, company_id bigint) returns text`, used by n8n via the read-only role (or a read query) and by the import.

The scope of "prior history" is the company if `company_id` is set, otherwise the contact.

1. No prior opportunity with stage outcome `won` → `new_business`
2. A won opportunity exists with `service_end_date >= current_date` → `upsell`
3. Latest won `service_end_date` is within `continuation_threshold_days` before today → `continuation`
4. Otherwise → `win_back`
5. Won opportunities with null `service_end_date` → fall back to `won_at` as the end proxy and log a warning.

### 8.4 WF-03 Meeting → stage automation
Trigger: cal.com booking sync (the owner's existing workflow; extend it).
- If `meeting_kind = needs_analysis` and the linked opportunity is at stage `new` → move to `needs_analysis`.
- If `meeting_kind = demo` and the opportunity's stage position is < demo → move to `demo`.
- Never move backwards. Never move past `demo` automatically.
- Linking a meeting to an opportunity: match the attendee email to a contact → that contact's single open opportunity. If there are 0 or more than 1, leave it unlinked and create a task "Link meeting to opportunity".

Requires separate cal.com event types for needs analysis and DEMO (Q8).

### 8.5 WF-04 B2B audit tasks
Trigger: NocoDB webhook "after insert" on `participants`.
Guard: only if status = `candidate` and no open task exists with this `participant_id`.
- Create a task "Schedule audit with <name> (<company>)" assigned to the configured scheduler (Q5).
- When the audit `meeting` is booked and linked → set participant status to `audit_scheduled`.
- When an `assessments` row of type `audit` is created for the participant → set status to `audited`.

### 8.6 Lifecycle stage (DB logic)
Function `refresh_lifecycle_stage(contact_id)`, called by triggers on `leads`, `opportunities` and `consents`, plus a nightly full refresh:
- `customer`: the contact (directly, or as a participant) has a won opportunity with `service_end_date >= current_date`
- `former_customer`: has a won opportunity, none active
- `lead`: has at least one lead and no won opportunities
- `subscriber`: everything else

### 8.7 Last activity (DB logic)
Triggers update `contacts.last_activity_at = greatest(existing, event time)` on insert into `leads`, `form_submissions`, `activities`, `meeting_attendees`, `participants`, `assessments`, and on any update of `opportunities` (for its contact).

### 8.8 WF-05 GDPR retention (nightly)
- Select contacts where `last_activity_at < now() - retention_years` and `anonymized_at is null` and no active service.
- **MVP: report only.** Create a single task for the admin with the list. Do not anonymize automatically until the owner confirms the legal basis (Q9).
- Withdrawn newsletter consent → the contact is excluded from any marketing export immediately.

### 8.9 WF-06 Data quality (nightly)
Create tasks for:
- won opportunities without `service_end_date`
- open opportunities with no stage change for over 30 days (from `opportunity_stage_history`)
- contacts without email that have open opportunities

### 8.10 Stage history trigger
`AFTER INSERT OR UPDATE OF stage_id ON opportunities`: insert into `opportunity_stage_history`. It also sets `won_at` / `lost_at` from the stage outcome.

Bypass for import: if `current_setting('app.importing', true) = 'on'`, skip the insert (the import writes history itself with original dates).

---

## 9. Reporting views (read via `crm_readonly`)

| View | Answers |
|---|---|
| `v_funnel_by_source` | per source and magnet, per month: leads → SQL → opportunities → won, conversion % |
| `v_stage_durations` | average and median days per stage, from `opportunity_stage_history` |
| `v_sales_cycle` | days from `leads.received_at` to `won_at`, per segment and type |
| `v_revenue_by_type` | won amount per month split by `new_business` / `continuation` / `win_back` / `upsell` |
| `v_audit_to_course` | per B2B opportunity: audited participants vs enrolled; plus audit lines won vs course lines won |
| `v_lost_analysis` | lost reasons by stage, segment and source |
| `v_renewals_upcoming` | won opportunities with `service_end_date` in the next 60 days and no newer open opportunity for the same contact/company |
| `v_referral_network` | referrers, referred contacts and companies, and resulting won revenue |
| `v_job_changes` | former participants (`company_contacts.ended_at` set) who now have a current company with no opportunity, i.e. referral prospects |

Legacy rows with `type = 'unknown'` and `lead_source = Legacy` must be filterable (include `import_source` in the views).

---

## 10. Phase 2 (out of MVP; design only, do not build)

- **WF-07 Email continuation agent:** the client emails "I want more" → forwarded to an n8n inbox → LLM (OpenRouter) detects intent only → match the sender to a contact → `compute_opportunity_type` → create an `ai_suggestions` row for salesperson approval (not a direct opportunity).
- Tables: `ai_runs` (model, cost, input, output, latency), `ai_suggestions` (proposed action, payload, status, reviewed_by), `embeddings` (pgvector), `automation_events`, `tags` plus join tables, `campaigns`, `campaign_members`, `touchpoints`.
- Job-change monitoring agent feeding `v_job_changes`.

---

## 11. Legacy import (`old-crm.xls`)

The owner has an existing import script and will adapt it. This section is its specification.

### 11.1 Approach
1. Load the raw sheet into schema `staging` (`staging.old_crm`), with all columns as `text`, unmodified.
2. Transform with SQL inside **one transaction**, with `SET LOCAL app.importing = 'on'`.
3. **Disable NocoDB webhooks** (or pause n8n) for the duration of the import.
4. Write directly via SQL (exception to AD-2).
5. Set `import_source = 'old_crm_xls'` and `legacy_id = <ID column>` on every created row. Reruns must be idempotent (upsert on `(import_source, legacy_id)`).
6. Write problems to `import_issues`, never silently drop rows.
7. After the import: re-enable webhooks, run "Sync metadata" in NocoDB, run `refresh_lifecycle_stage` for all contacts.

### 11.2 Parsing rules
- Dates are in **M/D/YYYY** format (e.g. `5/18/2026`). Parse with an explicit format, never locale guessing.
- Times are in `h:mm:ss AM/PM` format. Combine `Data wpłynięcia` + `Godzina wpłynięcia` into a timestamptz in `Europe/Warsaw`.
- Header cells contain line breaks and trailing spaces (e.g. `"Handlowiec\n"`, `"Data \nDEMO"`). Normalize headers (collapse whitespace, trim) before mapping.
- Empty strings → NULL.

### 11.3 Column mapping (each row = 1 contact + 0..1 company + 1 lead + 0..1 opportunity)

| Excel column | Target |
|---|---|
| `ID` | `legacy_id` on lead and opportunity |
| `Nazwa klienta` | B2C: contact name (split into first/last). B2B: ignored if `Organizacja` is present, else company name |
| `Organizacja` | `companies.name` |
| `Folder klienta` | `companies.sharepoint_url` (B2B) / `contacts.sharepoint_url` (B2C) |
| `B2B / B2C` | `leads.segment`, `opportunities.segment` |
| `Handlowiec` | `owner_id` → `team_members` by name (create missing members, warn) |
| `Branża` | `companies.industry` (B2B) / `contacts.industry` (B2C) |
| `Źródło` | `lead_source_id` (create missing sources) |
| `Forma kontaktu` | `leads.contact_method` (`Bookings` → `ms_bookings`; unmapped → `other` + warning) |
| `Kwalifikacja lead'a` | `leads.qualification_status` (MQL → `mql`, SQL → `sql`) |
| `Powód braku kwalifikacji lead'a` | `disqualification_reason_id` (create missing) and status `disqualified` |
| `Osoba kontaktowa` | B2B: contact name (split) |
| `Nr telefonu`, `E.mail` | `contacts.phone`, `contacts.email` |
| `Data wpłynięcia` + `Godzina wpłynięcia` | `leads.received_at`, `form_submissions.received_at` (channel `import`) |
| `Data utworzenia klienta` | `contacts.created_at` |
| `Data szansy sprzedaży` | `opportunities.created_at` + history row → `new` |
| `Data archiwizacji` | `opportunities.archived_at` |
| `Data badania potrzeb` | history row → `needs_analysis` |
| `Data DEMO` | history row → `demo` |
| `Data wysłania oferty` | history row → `proposal_sent` |
| `Data omówienia oferty` | history row → `proposal_review` |
| `Data wysłania umowy` | history row → `contract_sent` |
| `Data podpisania umowy` | history row → `won`, `won_at` |
| `Data utracenia` | history row → `lost`, `lost_at` |
| `Powód utraty szansy` | `lost_reason_id` (normalize free text; create missing; warn on near-duplicates) |
| `Etap` | current `stage_id` (map display names to keys; see 6.3) |
| `Stan` | consistency check: `zamknięta` must correspond to won/lost, `otwarta` to an open stage |
| `Data planowanego działania` + `Planowane działanie` | `tasks` (only for open opportunities) |
| `Szansa sprzedaży Wartość` | `opportunities.amount` |
| `Szansa sprzedaży . Etykieta` | `opportunities.type` (map known labels; empty/unknown → `unknown`) |
| `Notatki` | `activities` (type `note`, `occurred_at` = latest known date in the row) |
| `Spr. ID` | **unknown meaning (Q4)**; store in `import_issues` / staging, do not map |

### 11.4 Import rules
- **Contact dedupe:** by lower(email). Rows without email → create the contact and log a warning for manual review. Fuzzy name matching is reported, not merged.
- **Company dedupe:** by lower(trim(name)). Near-duplicates are reported.
- **Opportunity existence:** create an opportunity only if `Data szansy sprzedaży` or any stage date is present. Rows with only lead data → lead without opportunity.
- **Qualification consistency:** if an opportunity exists, the lead status must be at least `sql`. Upgrade it and log a warning (e.g. legacy ID 1638 is MQL but has an offer).
- **Stage history:** insert one history row per non-empty stage date, ordered by date, with `changed_by = 'import'`. If a later stage has an earlier date than a previous stage → log an `error` to `import_issues` (still import).
- **Current stage:** take it from `Etap`. If it is empty, use the latest stage with a date.
- **Type:** from `Etykieta` if mappable, else `unknown`. Do not back-compute types for legacy rows. An optional, separate, reviewable script may suggest types from gaps between consecutive opportunities of the same contact.
- **`source_lead_id`:** set on the imported opportunity (each legacy row is lead + opportunity).
- **Lead source:** if `Źródło` is empty → `Legacy`.
- **GDPR:** skip contacts with no activity for over 5 years (latest date in the row). Imported contacts get **no** marketing consent unless evidence exists.
- **Dry-run mode:** the script must support `--dry-run` (rolls back, prints counts and issues).

---

## 12. Delivery plan and acceptance criteria

### M1 — Schema
- Migrations for all tables in section 6 (except `assessments` result fields until Q6 is answered), seeds, triggers (8.6, 8.7, 8.10, `updated_at`), the function `compute_opportunity_type`, and the roles `crm_readonly` and the NocoDB role.
- **AC:** migrations run up/down cleanly on an empty DB; NocoDB metadata sync shows all tables; the AD-10 rendering check is reported; the ID-preservation check (AD-1) is reported.

### M2 — Import
- Staging load plus transform per section 11, with dry-run.
- **AC:** row counts reconcile (legacy rows = leads created; issues logged for every skipped/changed row); legacy ID 1639 has 7 history rows and stage `won`; legacy ID 1638 is a `sql` lead with an open opportunity at `proposal_review`; rerunning the import creates no duplicates.

### M3 — Automations
- WF-01, WF-02, WF-03 (extending the owner's cal.com sync), WF-04, WF-05 (report only), WF-06.
- **AC (scenario tests on staging data):**
  1. Rafał submits the form "for myself" → contact plus B2C lead plus task; submitting again with the same email → no new contact.
  2. The salesperson sets the lead to SQL → exactly one opportunity, type `new_business`, stage `new`; setting SQL again → nothing new.
  3. Rafał's opportunity is won with `service_end_date` = yesterday → a new opportunity for Rafał computes `continuation`; with end date 10 months ago → `win_back`; with an active service → `upsell`.
  4. Super Korpo: one opportunity with lines audit ×15 and course ×15; 15 participants → 15 audit tasks; 15 audit assessments → all participants `audited`; course line `quantity_won = 10`; 10 participants `enrolled`, 5 `not_enrolled`; `v_audit_to_course` shows 15 → 10.
  5. Audits only: audit line won, course line lost with reason → the opportunity can be won and reports show the course as lost.
  6. A booked cal.com DEMO for a contact with one open opportunity at `needs_analysis` → stage `demo`, and a history row exists.
  7. No webhook loops: every scenario finishes with a bounded number of workflow executions.

### M4 — Views and NocoDB UI
- Views from section 9 and NocoDB views from section 7.
- **AC:** every view returns data on the imported dataset; the Dorota Board kanban works; the read-only fields are not editable.

---

## 13. Open questions (ask the owner; do not assume)

| # | Question | Blocks |
|---|---|---|
| Q1 | Threshold in days between `continuation` and `win_back` (suggested 60–90, business decision) | 8.3 |
| Q2 | When the course contract is signed, are audits billed separately or included in the price? (drives `assessments.billable` defaults) | 8.5 |
| Q3 | "Person learns, company pays" (benefits): confirm the `payer` field approach and the segment for such cases | 6.3 |
| Q4 | Meaning of the Excel column `Spr. ID`; can one client have multiple rows? | 11.3 |
| Q5 | Who schedules audits vs who conducts them (Dorota's role)? | 8.5 |
| Q6 | Names of the 5 short text and 3 long text audit result fields; values of the assessment type single select | 6.4 |
| Q7 | Which tool powers the website forms and the newsletter; exact form fields | 8.1 |
| Q8 | cal.com event types: separate types for trial lesson, needs analysis, DEMO, audit? | 8.4 |
| Q9 | Legal confirmation of retention: 5 years for customers (accounting) vs consent-based for subscribers | 8.8 |
| Q10 | Migration tool preference (dbmate suggested) and Postgres version on the VPS | M1 |
| Q11 | Does HR provide the full participant list upfront, or do participants arrive gradually? | 8.5 |
| Q12 | Full list of values used in the Excel columns `Etykieta`, `Etap`, `Źródło`, `Forma kontaktu` (run `SELECT DISTINCT` on staging and show the owner) | 11.3 |