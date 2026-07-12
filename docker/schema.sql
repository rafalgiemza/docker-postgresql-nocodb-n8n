-- ============================================================================
-- CoAction CRM — schemat bazy danych appdata
-- Target: PostgreSQL 16+
-- Usage:  wgrywane przez docker/app_migrate.sh
--         (psql --username appdata_owner --dbname appdata < ./schema.sql)
--
-- Faza testowa (greenfield, .ai/IMPLEMENTATION_PLAN.md §3): plik jest w pełni
-- re-runnable — zaczyna się od DROP SCHEMA ... CASCADE, więc bezpiecznie
-- odpalać go wielokrotnie podczas iteracji. Gdy powstanie pierwsze środowisko
-- z danymi do zachowania, przejście na wersjonowane migracje (dbmate) wraca
-- jako ostatni krok FAZY 6.
--
-- Źródło prawdy dla modelu danych: .ai/PRD.md §2. Pliki w old-sql/ są
-- wyłącznie referencją koncepcyjną wcześniejszego szkicu, nie migrowane 1:1.
--
-- Role użyte w GRANT-ach niżej (docker/.env.example, docker/init-data.sh):
--   appdata_owner    — właściciel appdata, uruchamia ten plik (APPDATA_OWNER_USER)
--   nocodb_crm_user  — rola NocoDB, dostęp tylko do schematu crm.* (NOCODB_CRM_USER)
-- ============================================================================

BEGIN;

DROP SCHEMA IF EXISTS crm CASCADE;
DROP SCHEMA IF EXISTS appdata CASCADE;

CREATE SCHEMA appdata;
CREATE SCHEMA crm;

CREATE EXTENSION IF NOT EXISTS citext SCHEMA appdata;
CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA appdata;

SET search_path = appdata, crm, public;

DO $$
BEGIN
    EXECUTE format('ALTER DATABASE %I SET search_path = appdata, crm, public', current_database());
END $$;

-- ============================================================================
-- 1. Enumy (PRD §2.1)
-- ============================================================================

CREATE TYPE appdata.client_type AS ENUM ('B2B', 'B2C');

CREATE TYPE appdata.lead_source AS ENUM (
    'google', 'referral', 'linkedin', 'website', 'inbound_call', 'partner', 'other'
);

CREATE TYPE appdata.contact_form AS ENUM ('booking', 'email', 'phone', 'form', 'walk_in');

CREATE TYPE appdata.lead_qualif AS ENUM ('MQL', 'SQL', 'DISQUALIFIED', 'UNQUALIFIED');

-- Uwaga: daty etapów NIE są kolumnami na opportunities (legacy Excel miał 11
-- kolumn Data_*) — idą do opportunity_stage_history (append-only log).
CREATE TYPE appdata.opp_stage AS ENUM (
    'nowa', 'badanie_potrzeb', 'demo', 'przygotowanie_oferty', 'oferta_wyslana',
    'omowienie_oferty', 'umowa_wyslana', 'umowa_podpisana', 'utracona', 'archiwum'
);

CREATE TYPE appdata.opp_state AS ENUM ('otwarta', 'zamknieta', 'wstrzymana');

CREATE TYPE appdata.task_status AS ENUM ('todo', 'in_progress', 'blocked', 'done', 'cancelled');

CREATE TYPE appdata.transcript_src AS ENUM ('manual_paste', 'asr_auto', 'upload_file');

CREATE TYPE appdata.offer_status AS ENUM ('draft', 'ready', 'sent', 'accepted', 'rejected', 'superseded');

CREATE TYPE appdata.rec_type AS ENUM (
    'business_english', 'english_for_it', 'english_plus_skills', 'skills_only', 'mixed'
);

CREATE TYPE appdata.lesson_format AS ENUM ('1-1', 'pair', 'group');

CREATE TYPE appdata.job_status AS ENUM ('queued', 'running', 'done', 'failed');

-- ============================================================================
-- 2. Trigger helper
-- ============================================================================

CREATE FUNCTION appdata.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

-- ============================================================================
-- 3. Rdzeń: users → organizations → people → clients (PRD §2.2)
-- ============================================================================

-- users: brak w PRD §2, ale FK'owana z 8 miejsc (clients.owner_user_id,
-- opportunity_stage_history.changed_by, audits.auditor_user_id,
-- extractions.accepted_by, recommendations.approved_by, tasks.assignee_user_id,
-- offer_templates.uploaded_by, offers.created_by, files.uploaded_by) —
-- zaprojektowana od zera, wzorowana na old-sql/schema.sql.
CREATE TABLE appdata.users (
    id          bigserial PRIMARY KEY,
    full_name   text NOT NULL,
    email       citext NOT NULL UNIQUE,
    role        text NOT NULL CHECK (role IN ('sales', 'auditor', 'methodologist', 'admin', 'bot')),
    active      boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON appdata.users
    FOR EACH ROW EXECUTE FUNCTION appdata.set_updated_at();

CREATE TABLE appdata.organizations (
    id                bigserial PRIMARY KEY,
    name              text NOT NULL,
    industry          text,
    size_bucket       text CHECK (size_bucket IN ('<50', '50-250', '250+')),
    nip               text,
    business_context  jsonb,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE appdata.people (
    id               bigserial PRIMARY KEY,
    organization_id  bigint REFERENCES appdata.organizations (id),
    first_name       text,
    last_name        text,
    email            citext,
    phone            text,
    job_title        text,
    linkedin_url     text,
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_people_organization_id ON appdata.people (organization_id);
CREATE UNIQUE INDEX idx_people_email_unique ON appdata.people (email) WHERE email IS NOT NULL;

-- id: bigserial (nie GENERATED ALWAYS AS IDENTITY) — legacy rekordy (np.
-- 1638/1639) wstawiane z jawnym id przy migracji danych z Excela (Faza 6),
-- potem setval na sekwencji; bigserial nie wymaga OVERRIDING SYSTEM VALUE.
CREATE TABLE appdata.clients (
    id                        bigserial PRIMARY KEY,
    type                      appdata.client_type NOT NULL,
    organization_id           bigint REFERENCES appdata.organizations (id),
    primary_contact_id        bigint REFERENCES appdata.people (id),
    owner_user_id             bigint REFERENCES appdata.users (id),
    source                    appdata.lead_source,
    contact_form              appdata.contact_form,
    qualification             appdata.lead_qualif,
    disqualification_reason   text,
    minio_prefix              text,
    inbound_at                timestamptz,
    created_at                timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_clients_organization_id ON appdata.clients (organization_id);
CREATE INDEX idx_clients_owner_user_id ON appdata.clients (owner_user_id);
CREATE INDEX idx_clients_primary_contact_id ON appdata.clients (primary_contact_id);

-- ============================================================================
-- 4. Files (przeniesione przed transcripts/offer_snapshots, które je FK'ują)
-- ============================================================================

CREATE TABLE appdata.files (
    id           bigserial PRIMARY KEY,
    bucket       text NOT NULL,
    key          text NOT NULL,
    mime         text,
    size_bytes   bigint,
    sha256       text,
    uploaded_by  bigint REFERENCES appdata.users (id),
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_files_bucket_key ON appdata.files (bucket, key);

-- ============================================================================
-- 5. Pricing i szablony ofert (przeniesione przed offers, które je FK'ują)
-- ============================================================================

CREATE TABLE appdata.pricing_tiers (
    id          bigserial PRIMARY KEY,
    product     text NOT NULL,
    hours       integer NOT NULL CHECK (hours > 0),
    format      appdata.lesson_format NOT NULL,
    price_pln   numeric(10, 2) NOT NULL,
    valid_from  date NOT NULL,
    valid_to    date,
    CONSTRAINT uq_pricing_tiers_natural_key UNIQUE (product, hours, format, valid_from)
);

CREATE TABLE appdata.offer_templates (
    id                    bigserial PRIMARY KEY,
    name                  text NOT NULL,
    variant               text CHECK (variant IN ('b2c', 'b2b', 'continuation', 'special')),
    minio_key             text,
    version               integer NOT NULL DEFAULT 1,
    placeholder_manifest  jsonb,
    slide_map             jsonb,
    active                boolean NOT NULL DEFAULT true,
    uploaded_by           bigint REFERENCES appdata.users (id),
    created_at            timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 6. Opportunities + historia etapów (PRD §2.2)
-- ============================================================================

CREATE TABLE appdata.opportunities (
    id              bigserial PRIMARY KEY,
    client_id       bigint NOT NULL REFERENCES appdata.clients (id),
    stage           appdata.opp_stage NOT NULL DEFAULT 'nowa',
    state           appdata.opp_state NOT NULL DEFAULT 'otwarta',
    value_pln       numeric(10, 2),
    label           text,
    next_action_at  date,
    next_action     text,
    loss_reason     text,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_opportunities_client_id ON appdata.opportunities (client_id);
CREATE INDEX idx_opportunities_stage ON appdata.opportunities (stage);

CREATE TRIGGER trg_opportunities_updated_at
    BEFORE UPDATE ON appdata.opportunities
    FOR EACH ROW EXECUTE FUNCTION appdata.set_updated_at();

CREATE TABLE appdata.opportunity_stage_history (
    id              bigserial PRIMARY KEY,
    opportunity_id  bigint NOT NULL REFERENCES appdata.opportunities (id),
    from_stage      appdata.opp_stage,
    to_stage        appdata.opp_stage NOT NULL,
    changed_by      bigint REFERENCES appdata.users (id),  -- NULL = system/n8n/NocoDB
    changed_at      timestamptz NOT NULL DEFAULT now(),
    note            text
);

CREATE INDEX idx_opportunity_stage_history_opportunity_id
    ON appdata.opportunity_stage_history (opportunity_id, changed_at);

CREATE FUNCTION appdata.log_opportunity_stage_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO appdata.opportunity_stage_history (opportunity_id, from_stage, to_stage, changed_by)
    VALUES (NEW.id, OLD.stage, NEW.stage, NULL);
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_opportunities_stage_history
    AFTER UPDATE OF stage ON appdata.opportunities
    FOR EACH ROW
    WHEN (OLD.stage IS DISTINCT FROM NEW.stage)
    EXECUTE FUNCTION appdata.log_opportunity_stage_change();

-- ============================================================================
-- 7. Discovery (PRD §2.3)
-- ============================================================================

CREATE TABLE appdata.discovery_calls (
    id                  bigserial PRIMARY KEY,
    opportunity_id      bigint NOT NULL REFERENCES appdata.opportunities (id),
    scheduled_at        timestamptz,
    ended_at            timestamptz,
    duration_min        integer,
    external_event_id   text,
    meeting_url         text,
    attendees           jsonb
);

CREATE INDEX idx_discovery_calls_opportunity_id ON appdata.discovery_calls (opportunity_id);

-- ============================================================================
-- 8. Audyt i rekomendacje (PRD §2.4)
-- ============================================================================

CREATE TABLE appdata.participants (
    id                         bigserial PRIMARY KEY,
    client_id                  bigint NOT NULL REFERENCES appdata.clients (id),
    person_id                  bigint REFERENCES appdata.people (id),
    manager_needs              text,
    self_assessment            jsonb,
    communication_situations   text[]
);

CREATE INDEX idx_participants_client_id ON appdata.participants (client_id);

CREATE TABLE appdata.audits (
    id               bigserial PRIMARY KEY,
    participant_id   bigint NOT NULL REFERENCES appdata.participants (id),
    opportunity_id   bigint NOT NULL REFERENCES appdata.opportunities (id),
    auditor_user_id  bigint REFERENCES appdata.users (id),
    conducted_at     timestamptz,
    observations     text,
    strengths        text[],
    gaps             text[],
    scope            jsonb,
    status           text NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'done'))
);

CREATE INDEX idx_audits_participant_id ON appdata.audits (participant_id);
CREATE INDEX idx_audits_opportunity_id ON appdata.audits (opportunity_id);

-- Dokładnie 5 wymiarów, jeden wiersz per (audit, dimension). cefr_numeric
-- (A1=1.0 … C2=6.0 + cefr_decimal) ułatwia sortowanie/porównania w NocoDB,
-- cefr_level/cefr_decimal razem renderują się jako np. "B2.6".
CREATE TABLE appdata.audit_scores (
    id             bigserial PRIMARY KEY,
    audit_id       bigint NOT NULL REFERENCES appdata.audits (id),
    dimension      text NOT NULL CHECK (dimension IN ('overall', 'range', 'accuracy', 'fluency', 'communicativeness')),
    cefr_level     text NOT NULL CHECK (cefr_level IN ('A1', 'A2', 'B1', 'B2', 'C1', 'C2')),
    cefr_decimal   numeric(2, 1) NOT NULL DEFAULT 0 CHECK (cefr_decimal >= 0 AND cefr_decimal < 1),
    cefr_numeric   numeric GENERATED ALWAYS AS (
        (CASE cefr_level
            WHEN 'A1' THEN 1.0 WHEN 'A2' THEN 2.0 WHEN 'B1' THEN 3.0
            WHEN 'B2' THEN 4.0 WHEN 'C1' THEN 5.0 WHEN 'C2' THEN 6.0
        END) + cefr_decimal
    ) STORED,
    justification  text,
    CONSTRAINT uq_audit_scores_audit_dimension UNIQUE (audit_id, dimension)
);

CREATE TABLE appdata.recommendations (
    id                       bigserial PRIMARY KEY,
    opportunity_id           bigint NOT NULL REFERENCES appdata.opportunities (id),
    audit_id                 bigint REFERENCES appdata.audits (id),
    type                     appdata.rec_type,
    headline                 text,
    situation_description    text,
    rationale                text,
    priority                 integer,
    approved_by              bigint REFERENCES appdata.users (id),
    approved_at              timestamptz  -- gate do oferty
);

CREATE INDEX idx_recommendations_opportunity_id ON appdata.recommendations (opportunity_id);
CREATE INDEX idx_recommendations_audit_id ON appdata.recommendations (audit_id);

CREATE TABLE appdata.recommendation_goals (
    id                  bigserial PRIMARY KEY,
    recommendation_id   bigint NOT NULL REFERENCES appdata.recommendations (id),
    position             integer NOT NULL,
    title                text,
    body                 text,
    stage_label          text,
    CONSTRAINT uq_recommendation_goals_position UNIQUE (recommendation_id, position)
);

-- ============================================================================
-- 9. Transkrypty i ekstrakcje AI (PRD §2.3)
-- ============================================================================

CREATE TABLE appdata.transcripts (
    id                   bigserial PRIMARY KEY,
    discovery_call_id    bigint REFERENCES appdata.discovery_calls (id),
    audit_id             bigint REFERENCES appdata.audits (id),
    source               appdata.transcript_src NOT NULL,
    language             text[],
    raw_text             text,
    curated_text         text,
    recording_file_id    bigint REFERENCES appdata.files (id),
    -- 'simple', NIE 'polish' — transkrypty są dwujęzyczne (PL/EN), polski
    -- stemmer zniszczyłby angielskie terminy techniczne.
    search_tsv           tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(curated_text, raw_text, ''))
    ) STORED,
    created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_transcripts_search_tsv ON appdata.transcripts USING GIN (search_tsv);
CREATE INDEX idx_transcripts_curated_trgm ON appdata.transcripts USING GIN (curated_text appdata.gin_trgm_ops);

-- extractions: surowy output AI, oddzielny od danych zaakceptowanych przez
-- człowieka. accepted_at = brama — nic z extractions nie trafia do
-- opportunities/participants dopóki to nie jest ustawione.
CREATE TABLE appdata.extractions (
    id               bigserial PRIMARY KEY,
    transcript_id    bigint NOT NULL REFERENCES appdata.transcripts (id),
    model            text,
    prompt_version   text,
    payload          jsonb NOT NULL,
    accepted_by      bigint REFERENCES appdata.users (id),
    accepted_at      timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_extractions_transcript_id ON appdata.extractions (transcript_id);

-- ============================================================================
-- 10. Oferty, pozycje ofert, trigger cenowy (PRD §2.5)
-- ============================================================================

CREATE TABLE appdata.offers (
    id                        bigserial PRIMARY KEY,
    opportunity_id            bigint NOT NULL REFERENCES appdata.opportunities (id),
    recommendation_id         bigint REFERENCES appdata.recommendations (id),
    template_id               bigint REFERENCES appdata.offer_templates (id),
    version                   integer NOT NULL DEFAULT 1,
    status                    appdata.offer_status NOT NULL DEFAULT 'draft',
    total_hours               integer NOT NULL DEFAULT 0,      -- trigger, nigdy z frontendu
    total_price_pln           numeric(10, 2) NOT NULL DEFAULT 0, -- trigger, nigdy z frontendu
    discount_pct              numeric(4, 2) NOT NULL DEFAULT 0,
    valid_until               date,
    included_testimonial_ids  bigint[],
    included_sections         text[],
    custom_notes              text,
    created_by                bigint REFERENCES appdata.users (id),
    created_at                timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_offers_opportunity_version UNIQUE (opportunity_id, version)
);

CREATE INDEX idx_offers_opportunity_id ON appdata.offers (opportunity_id);
CREATE INDEX idx_offers_recommendation_id ON appdata.offers (recommendation_id);

-- Max 2 pozycje na ofertę w praktyce (wszystkie przykłady PRD, np. oferta
-- 1638 = 60h BE + 15h warsztat) — nie jest to twarde ograniczenie schematu
-- (position nie jest capped), ale crm.v_offer_builder niżej zakłada dokładnie
-- position IN (1, 2).
CREATE TABLE appdata.offer_items (
    id                bigserial PRIMARY KEY,
    offer_id          bigint NOT NULL REFERENCES appdata.offers (id),
    position          integer NOT NULL,
    product           text,
    label             text,
    hours             integer,
    format            appdata.lesson_format,
    pricing_tier_id   bigint REFERENCES appdata.pricing_tiers (id),
    unit_price_pln    numeric(10, 2),  -- kopiowane triggerem z pricing_tiers
    CONSTRAINT uq_offer_items_position UNIQUE (offer_id, position)
);

CREATE INDEX idx_offer_items_offer_id ON appdata.offer_items (offer_id);

-- Cena nigdy nie przychodzi z NocoDB ani n8n — baza liczy sama (PRD §2.5).
CREATE FUNCTION appdata.set_offer_item_unit_price()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.pricing_tier_id IS NOT NULL THEN
        SELECT price_pln INTO NEW.unit_price_pln
        FROM appdata.pricing_tiers
        WHERE id = NEW.pricing_tier_id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_offer_items_set_unit_price
    BEFORE INSERT OR UPDATE ON appdata.offer_items
    FOR EACH ROW EXECUTE FUNCTION appdata.set_offer_item_unit_price();

CREATE FUNCTION appdata.recalc_offer_totals(p_offer_id bigint)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE appdata.offers o
    SET total_hours = agg.total_hours,
        total_price_pln = round(agg.total_price * (1 - o.discount_pct / 100), 2)
    FROM (
        SELECT
            coalesce(sum(hours), 0) AS total_hours,
            coalesce(sum(unit_price_pln), 0) AS total_price
        FROM appdata.offer_items
        WHERE offer_id = p_offer_id
    ) agg
    WHERE o.id = p_offer_id;
END;
$$;

CREATE FUNCTION appdata.trg_offer_items_recalc_totals_fn()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM appdata.recalc_offer_totals(COALESCE(NEW.offer_id, OLD.offer_id));
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_offer_items_recalc_totals
    AFTER INSERT OR UPDATE OR DELETE ON appdata.offer_items
    FOR EACH ROW EXECUTE FUNCTION appdata.trg_offer_items_recalc_totals_fn();

-- Domknięcie tej samej reguły: discount_pct też jest UPDATE-owalny z NocoDB
-- (crm.v_offer_builder) — bez tego triggera total_price_pln zostałby stary
-- do czasu dotknięcia jakiejkolwiek pozycji oferty.
CREATE FUNCTION appdata.trg_offers_recalc_on_discount_fn()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM appdata.recalc_offer_totals(NEW.id);
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_offers_recalc_on_discount
    AFTER UPDATE OF discount_pct ON appdata.offers
    FOR EACH ROW
    WHEN (OLD.discount_pct IS DISTINCT FROM NEW.discount_pct)
    EXECUTE FUNCTION appdata.trg_offers_recalc_on_discount_fn();

-- ============================================================================
-- 11. Testimoniale i snapshoty ofert (PRD §2.5)
-- ============================================================================

CREATE TABLE appdata.testimonials (
    id                   bigserial PRIMARY KEY,
    author               text NOT NULL,
    role                 text,
    quote                text,
    tags                 text[],
    slide_template_idx   integer,
    active               boolean NOT NULL DEFAULT true
);

-- Część renderera PPTX/PDF jest poza zakresem MVP (patrz IMPLEMENTATION_PLAN.md
-- §6), ale tabela wchodzi w skład schematu bazowego — offers.template_id i
-- offer_snapshots muszą mieć do czego się odnosić.
CREATE TABLE appdata.offer_snapshots (
    id                 bigserial PRIMARY KEY,
    offer_id           bigint NOT NULL REFERENCES appdata.offers (id),
    version            integer NOT NULL,
    format             text CHECK (format IN ('pptx', 'pdf')),
    minio_key          text,
    sha256             text,
    payload_snapshot   jsonb,
    template_id        bigint REFERENCES appdata.offer_templates (id),
    template_version   integer,
    status             appdata.job_status NOT NULL DEFAULT 'queued',
    error              text,
    generated_at       timestamptz
);

CREATE INDEX idx_offer_snapshots_offer_id ON appdata.offer_snapshots (offer_id);

-- ============================================================================
-- 12. Taski i kolejka (PRD §2.6)
-- ============================================================================

CREATE TABLE appdata.tasks (
    id                bigserial PRIMARY KEY,
    entity_type       text NOT NULL CHECK (entity_type IN ('opportunity', 'audit', 'offer', 'transcript')),
    entity_id         bigint NOT NULL,
    assignee_user_id  bigint REFERENCES appdata.users (id),
    title             text NOT NULL,
    stage_ref         appdata.opp_stage,
    status            appdata.task_status NOT NULL DEFAULT 'todo',
    due_at            timestamptz,
    payload           jsonb,
    created_at        timestamptz NOT NULL DEFAULT now(),
    completed_at      timestamptz
);

CREATE INDEX idx_tasks_entity ON appdata.tasks (entity_type, entity_id);
CREATE INDEX idx_tasks_assignee_status ON appdata.tasks (assignee_user_id, status);

CREATE TABLE appdata.job_queue (
    id           bigserial PRIMARY KEY,
    kind         text NOT NULL,
    priority     integer NOT NULL DEFAULT 1,  -- 10=interaktywny, 3=AI, 1=batch
    payload      jsonb,
    status       appdata.job_status NOT NULL DEFAULT 'queued',
    attempts     integer NOT NULL DEFAULT 0,
    last_error   text,
    locked_at    timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- Partial index dopasowany dokładnie do zapytania konsumenta:
--   SELECT * FROM job_queue WHERE status='queued'
--   ORDER BY priority DESC, created_at ASC LIMIT 1 FOR UPDATE SKIP LOCKED;
CREATE INDEX idx_job_queue_dispatch
    ON appdata.job_queue (status, priority DESC, created_at)
    WHERE status = 'queued';

-- ============================================================================
-- 13. Widoki dla NocoDB — schemat crm.* (PRD §2.7)
--
-- NocoDB nigdy nie widzi tabel appdata.* bezpośrednio — pracuje wyłącznie na
-- tych widokach, przez nocodb_crm_user (patrz sekcja 14, granty).
--
-- Każda funkcja INSTEAD OF jest SECURITY DEFINER z ustawionym search_path —
-- bez tego nocodb_crm_user (REVOKE ALL ON SCHEMA appdata) dostałby
-- "permission denied for schema appdata" przy każdym UPDATE przez widok.
-- ============================================================================

-- v_pipeline: SELECT, UPDATE(stage, next_action, next_action_at, notes).
-- next_action_at dodane mimo że PRD §2.7 literalnie wymienia tylko
-- (stage, next_action, notes) — next_action (treść) i next_action_at (data)
-- to logiczna para, bez daty nie da się ustawić terminu z NocoDB.
CREATE VIEW crm.v_pipeline AS
SELECT
    o.id                  AS opportunity_id,
    o.stage,
    o.state,
    o.value_pln,
    o.label,
    o.next_action_at,
    o.next_action,
    o.notes,
    o.loss_reason,
    c.id                  AS client_id,
    c.type                AS client_type,
    c.qualification,
    p.first_name,
    p.last_name,
    p.email,
    org.name              AS organization_name,
    u.full_name           AS owner_name,
    o.created_at,
    o.updated_at
FROM appdata.opportunities o
JOIN appdata.clients c              ON c.id = o.client_id
LEFT JOIN appdata.people p          ON p.id = c.primary_contact_id
LEFT JOIN appdata.organizations org ON org.id = c.organization_id
LEFT JOIN appdata.users u           ON u.id = c.owner_user_id;

CREATE FUNCTION crm.v_pipeline_instead_of_update()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = appdata, crm, pg_temp
AS $$
BEGIN
    UPDATE appdata.opportunities
    SET stage          = NEW.stage,
        next_action_at = NEW.next_action_at,
        next_action    = NEW.next_action,
        notes          = NEW.notes
    WHERE id = NEW.opportunity_id;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_v_pipeline_instead_of_update
    INSTEAD OF UPDATE ON crm.v_pipeline
    FOR EACH ROW EXECUTE FUNCTION crm.v_pipeline_instead_of_update();

-- v_opportunity_dates: SELECT only. Pivot opportunity_stage_history po
-- to_stage, odtwarza układ 11 kolumn Data_* z legacy Excela.
CREATE VIEW crm.v_opportunity_dates AS
SELECT
    opportunity_id,
    max(changed_at) FILTER (WHERE to_stage = 'nowa')                  AS data_nowa,
    max(changed_at) FILTER (WHERE to_stage = 'badanie_potrzeb')       AS data_badanie_potrzeb,
    max(changed_at) FILTER (WHERE to_stage = 'demo')                  AS data_demo,
    max(changed_at) FILTER (WHERE to_stage = 'przygotowanie_oferty')  AS data_przygotowanie_oferty,
    max(changed_at) FILTER (WHERE to_stage = 'oferta_wyslana')        AS data_oferta_wyslana,
    max(changed_at) FILTER (WHERE to_stage = 'omowienie_oferty')      AS data_omowienie_oferty,
    max(changed_at) FILTER (WHERE to_stage = 'umowa_wyslana')         AS data_umowa_wyslana,
    max(changed_at) FILTER (WHERE to_stage = 'umowa_podpisana')       AS data_umowa_podpisana,
    max(changed_at) FILTER (WHERE to_stage = 'utracona')              AS data_utracona,
    max(changed_at) FILTER (WHERE to_stage = 'archiwum')              AS data_archiwum
FROM appdata.opportunity_stage_history
GROUP BY opportunity_id;

-- v_offer_builder: SELECT, UPDATE bez cen. Pola 1:1 ze slajdami (PRD §5).
-- Pivot pierwszych dwóch offer_items (position 1/2) do kolumn item1_*/item2_*
-- — założenie max 2 pozycji na ofertę, zgodne ze wszystkimi przykładami PRD.
-- total_hours/total_price_pln celowo tylko do odczytu (liczy je trigger).
CREATE VIEW crm.v_offer_builder AS
SELECT
    off.id                        AS offer_id,
    off.opportunity_id,
    off.recommendation_id,
    off.status,
    off.valid_until,
    off.discount_pct,
    off.total_hours,
    off.total_price_pln,
    off.custom_notes,
    off.included_testimonial_ids,
    off.included_sections,
    c.id                          AS client_id,
    c.type                        AS client_type,
    p.first_name,
    p.last_name,
    org.name                      AS organization_name,
    rec.headline,
    rec.situation_description,
    rec.type                      AS recommendation_type,
    sc_overall.cefr_level         AS cefr_overall,
    sc_range.cefr_level           AS cefr_range,
    sc_accuracy.cefr_level        AS cefr_accuracy,
    sc_fluency.cefr_level         AS cefr_fluency,
    sc_comm.cefr_level            AS cefr_communicativeness,
    item1.product                 AS item1_product,
    item1.label                   AS item1_label,
    item1.hours                   AS item1_hours,
    item1.format                  AS item1_format,
    item1.pricing_tier_id         AS item1_pricing_tier_id,
    item1.unit_price_pln          AS item1_price_pln,
    item2.product                 AS item2_product,
    item2.label                   AS item2_label,
    item2.hours                   AS item2_hours,
    item2.format                  AS item2_format,
    item2.pricing_tier_id         AS item2_pricing_tier_id,
    item2.unit_price_pln          AS item2_price_pln
FROM appdata.offers off
JOIN appdata.opportunities o              ON o.id = off.opportunity_id
JOIN appdata.clients c                    ON c.id = o.client_id
LEFT JOIN appdata.people p                ON p.id = c.primary_contact_id
LEFT JOIN appdata.organizations org       ON org.id = c.organization_id
LEFT JOIN appdata.recommendations rec     ON rec.id = off.recommendation_id
LEFT JOIN appdata.audit_scores sc_overall  ON sc_overall.audit_id = rec.audit_id  AND sc_overall.dimension = 'overall'
LEFT JOIN appdata.audit_scores sc_range    ON sc_range.audit_id = rec.audit_id    AND sc_range.dimension = 'range'
LEFT JOIN appdata.audit_scores sc_accuracy ON sc_accuracy.audit_id = rec.audit_id AND sc_accuracy.dimension = 'accuracy'
LEFT JOIN appdata.audit_scores sc_fluency  ON sc_fluency.audit_id = rec.audit_id  AND sc_fluency.dimension = 'fluency'
LEFT JOIN appdata.audit_scores sc_comm     ON sc_comm.audit_id = rec.audit_id     AND sc_comm.dimension = 'communicativeness'
LEFT JOIN appdata.offer_items item1 ON item1.offer_id = off.id AND item1.position = 1
LEFT JOIN appdata.offer_items item2 ON item2.offer_id = off.id AND item2.position = 2;

CREATE FUNCTION crm.v_offer_builder_instead_of_update()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = appdata, crm, pg_temp
AS $$
BEGIN
    UPDATE appdata.offers
    SET status                   = NEW.status,
        valid_until               = NEW.valid_until,
        discount_pct              = NEW.discount_pct,
        custom_notes              = NEW.custom_notes,
        included_testimonial_ids  = NEW.included_testimonial_ids,
        included_sections         = NEW.included_sections
    WHERE id = NEW.offer_id;

    IF NEW.item1_product IS NULL THEN
        DELETE FROM appdata.offer_items WHERE offer_id = NEW.offer_id AND position = 1;
    ELSE
        INSERT INTO appdata.offer_items (offer_id, position, product, label, hours, format, pricing_tier_id)
        VALUES (NEW.offer_id, 1, NEW.item1_product, NEW.item1_label, NEW.item1_hours, NEW.item1_format, NEW.item1_pricing_tier_id)
        ON CONFLICT (offer_id, position) DO UPDATE
        SET product = EXCLUDED.product,
            label = EXCLUDED.label,
            hours = EXCLUDED.hours,
            format = EXCLUDED.format,
            pricing_tier_id = EXCLUDED.pricing_tier_id;
    END IF;

    IF NEW.item2_product IS NULL THEN
        DELETE FROM appdata.offer_items WHERE offer_id = NEW.offer_id AND position = 2;
    ELSE
        INSERT INTO appdata.offer_items (offer_id, position, product, label, hours, format, pricing_tier_id)
        VALUES (NEW.offer_id, 2, NEW.item2_product, NEW.item2_label, NEW.item2_hours, NEW.item2_format, NEW.item2_pricing_tier_id)
        ON CONFLICT (offer_id, position) DO UPDATE
        SET product = EXCLUDED.product,
            label = EXCLUDED.label,
            hours = EXCLUDED.hours,
            format = EXCLUDED.format,
            pricing_tier_id = EXCLUDED.pricing_tier_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_v_offer_builder_instead_of_update
    INSTEAD OF UPDATE ON crm.v_offer_builder
    FOR EACH ROW EXECUTE FUNCTION crm.v_offer_builder_instead_of_update();

-- v_offer_goals: SELECT, INSERT, UPDATE, DELETE.
CREATE VIEW crm.v_offer_goals AS
SELECT
    rg.id            AS goal_id,
    rg.recommendation_id,
    rg.position,
    rg.title,
    rg.body,
    rg.stage_label,
    off.id           AS offer_id
FROM appdata.recommendation_goals rg
JOIN appdata.recommendations rec ON rec.id = rg.recommendation_id
LEFT JOIN appdata.offers off     ON off.recommendation_id = rec.id;

CREATE FUNCTION crm.v_offer_goals_instead_of()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = appdata, crm, pg_temp
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO appdata.recommendation_goals (recommendation_id, position, title, body, stage_label)
        VALUES (NEW.recommendation_id, NEW.position, NEW.title, NEW.body, NEW.stage_label)
        RETURNING id INTO NEW.goal_id;
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        UPDATE appdata.recommendation_goals
        SET recommendation_id = NEW.recommendation_id,
            position          = NEW.position,
            title             = NEW.title,
            body              = NEW.body,
            stage_label       = NEW.stage_label
        WHERE id = NEW.goal_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        DELETE FROM appdata.recommendation_goals WHERE id = OLD.goal_id;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_v_offer_goals_instead_of
    INSTEAD OF INSERT OR UPDATE OR DELETE ON crm.v_offer_goals
    FOR EACH ROW EXECUTE FUNCTION crm.v_offer_goals_instead_of();

-- v_audit_scores: SELECT, UPDATE(cefr_level, cefr_decimal, justification) —
-- nie cefr_numeric, bo to kolumna GENERATED.
CREATE VIEW crm.v_audit_scores AS
SELECT
    s.id             AS score_id,
    s.audit_id,
    s.dimension,
    s.cefr_level,
    s.cefr_decimal,
    s.cefr_numeric,
    s.justification,
    a.opportunity_id,
    p.first_name,
    p.last_name
FROM appdata.audit_scores s
JOIN appdata.audits a        ON a.id = s.audit_id
JOIN appdata.participants pt ON pt.id = a.participant_id
LEFT JOIN appdata.people p   ON p.id = pt.person_id;

CREATE FUNCTION crm.v_audit_scores_instead_of_update()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = appdata, crm, pg_temp
AS $$
BEGIN
    UPDATE appdata.audit_scores
    SET cefr_level    = NEW.cefr_level,
        cefr_decimal  = NEW.cefr_decimal,
        justification = NEW.justification
    WHERE id = NEW.score_id;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_v_audit_scores_instead_of_update
    INSTEAD OF UPDATE ON crm.v_audit_scores
    FOR EACH ROW EXECUTE FUNCTION crm.v_audit_scores_instead_of_update();

-- v_tasks: SELECT, UPDATE(status) — auto completed_at gdy status='done'.
CREATE VIEW crm.v_tasks AS
SELECT
    t.id               AS task_id,
    t.entity_type,
    t.entity_id,
    t.title,
    t.stage_ref,
    t.status,
    t.due_at,
    t.payload,
    t.created_at,
    t.completed_at,
    u.id               AS assignee_user_id,
    u.full_name        AS assignee_name
FROM appdata.tasks t
LEFT JOIN appdata.users u ON u.id = t.assignee_user_id;

CREATE FUNCTION crm.v_tasks_instead_of_update()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = appdata, crm, pg_temp
AS $$
BEGIN
    UPDATE appdata.tasks
    SET status       = NEW.status,
        completed_at = CASE WHEN NEW.status = 'done' THEN now() ELSE completed_at END
    WHERE id = NEW.task_id;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_v_tasks_instead_of_update
    INSTEAD OF UPDATE ON crm.v_tasks
    FOR EACH ROW EXECUTE FUNCTION crm.v_tasks_instead_of_update();

-- v_testimonials: SELECT only, katalog.
CREATE VIEW crm.v_testimonials AS
SELECT
    id AS testimonial_id, author, role, quote, tags, slide_template_idx, active
FROM appdata.testimonials;

-- v_pricing: SELECT only, aktualny cennik.
CREATE VIEW crm.v_pricing AS
SELECT
    id AS pricing_tier_id, product, hours, format, price_pln, valid_from, valid_to
FROM appdata.pricing_tiers
WHERE valid_to IS NULL OR valid_to >= CURRENT_DATE;

-- ============================================================================
-- 13.5. Notatki do szans sprzedaży: appdata.opportunity_notes + crm.v_opportunity_notes
--
-- Poza PRD/IMPLEMENTATION_PLAN.md — decyzja z 2026-07-12: historia notatek po
-- spotkaniu, powiązana z leadem/opportunity. Wiele wpisów w czasie, nic nie
-- jest nadpisywane (w przeciwieństwie do opportunities.notes, pojedynczego
-- pola nadpisywanego przy każdej edycji przez crm.v_pipeline). Tylko SELECT +
-- INSERT — to log historyczny jak appdata.opportunity_stage_history (bez
-- UPDATE/DELETE), nie edytowalny rekord.
-- ============================================================================

CREATE TABLE appdata.opportunity_notes (
    id              bigserial PRIMARY KEY,
    opportunity_id  bigint NOT NULL REFERENCES appdata.opportunities (id),
    author_user_id  bigint REFERENCES appdata.users (id),
    body            text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_opportunity_notes_opportunity_id
    ON appdata.opportunity_notes (opportunity_id, created_at);

CREATE VIEW crm.v_opportunity_notes AS
SELECT
    n.id            AS note_id,
    n.opportunity_id,
    n.author_user_id,
    u.full_name     AS author_name,
    n.body,
    n.created_at
FROM appdata.opportunity_notes n
LEFT JOIN appdata.users u ON u.id = n.author_user_id;

CREATE FUNCTION crm.v_opportunity_notes_instead_of_insert()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = appdata, crm, pg_temp
AS $$
BEGIN
    INSERT INTO appdata.opportunity_notes (opportunity_id, author_user_id, body)
    VALUES (NEW.opportunity_id, NEW.author_user_id, NEW.body)
    RETURNING id, created_at INTO NEW.note_id, NEW.created_at;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_v_opportunity_notes_instead_of_insert
    INSTEAD OF INSERT ON crm.v_opportunity_notes
    FOR EACH ROW EXECUTE FUNCTION crm.v_opportunity_notes_instead_of_insert();

-- ============================================================================
-- 14. Granty dla nocodb_crm_user (PRD §8.2 — obrona przed schema drift)
--
-- NocoDB podpięty do zewnętrznego Postgresa potrafi zmodyfikować schemat przy
-- "Sync" — dlatego nocodb_crm_user nigdy nie ma praw do appdata.*/public,
-- tylko do widoków w crm.*. Bez ALTER DEFAULT PRIVILEGES celowo (fail-closed)
-- — każdy przyszły widok dostaje jawny GRANT dopisany tutaj.
-- ============================================================================

REVOKE ALL ON SCHEMA appdata FROM nocodb_crm_user;
REVOKE ALL ON SCHEMA public  FROM nocodb_crm_user;

GRANT USAGE ON SCHEMA crm TO nocodb_crm_user;

GRANT SELECT, UPDATE                  ON crm.v_pipeline           TO nocodb_crm_user;
GRANT SELECT, UPDATE                  ON crm.v_offer_builder      TO nocodb_crm_user;
GRANT SELECT, INSERT, UPDATE, DELETE  ON crm.v_offer_goals        TO nocodb_crm_user;
GRANT SELECT, UPDATE                  ON crm.v_audit_scores       TO nocodb_crm_user;
GRANT SELECT, UPDATE                  ON crm.v_tasks              TO nocodb_crm_user;
GRANT SELECT                          ON crm.v_testimonials       TO nocodb_crm_user;
GRANT SELECT                          ON crm.v_pricing            TO nocodb_crm_user;
GRANT SELECT                          ON crm.v_opportunity_dates  TO nocodb_crm_user;
GRANT SELECT, INSERT                  ON crm.v_opportunity_notes  TO nocodb_crm_user;

-- ============================================================================
-- 15. Granty dla n8n_crm_user (IMPLEMENTATION_PLAN.md §FAZA 3/5 — WF-1..WF-6)
--
-- Osobna rola od nocodb_crm_user, żeby n8n i NocoDB zostały rozróżnialne w
-- pg_stat_activity/logach i żeby zaostrzanie uprawnień jednego nie dotykało
-- drugiego. WF-6 (okrojone) potrzebuje tylko crm.v_offer_builder.
--
-- WF-1..WF-5 (docker/n8n-workflows/wf1..wf5-*.json) piszą prosto do
-- appdata.* zamiast przez crm.v_* — to n8n jako "system" (PRD: changed_by =
-- NULL = system/n8n), nie NocoDB, więc nie potrzeba tu warstwy
-- INSTEAD OF-widoków chroniących przed schema drift (to problem tylko
-- zewnętrznego "Sync" NocoDB, patrz sekcja 14/PRD §8.2). Zakres per tabela
-- ograniczony do operacji, których faktycznie używają te workflowy — bez
-- DELETE nigdzie, bez dostępu do offers/offer_items/pricing_tiers (to broni
-- crm.v_offer_builder, patrz sekcja 13, i NIE powinno być pisane z n8n
-- omijając trigger cenowy).
-- ============================================================================

REVOKE ALL ON SCHEMA appdata FROM n8n_crm_user;
REVOKE ALL ON SCHEMA public  FROM n8n_crm_user;

GRANT USAGE ON SCHEMA crm TO n8n_crm_user;

GRANT SELECT, UPDATE ON crm.v_offer_builder TO n8n_crm_user;

GRANT USAGE ON SCHEMA appdata TO n8n_crm_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA appdata TO n8n_crm_user;

GRANT SELECT                ON appdata.users                     TO n8n_crm_user;
GRANT SELECT, INSERT, UPDATE ON appdata.organizations             TO n8n_crm_user; -- UPDATE(business_context) w WF-4
GRANT SELECT, INSERT        ON appdata.people                     TO n8n_crm_user;
GRANT SELECT, INSERT        ON appdata.clients                    TO n8n_crm_user;
GRANT SELECT, INSERT, UPDATE ON appdata.opportunities             TO n8n_crm_user; -- UPDATE(stage) only, patrz WF-2/3
GRANT SELECT, INSERT        ON appdata.opportunity_stage_history   TO n8n_crm_user; -- log_opportunity_stage_change() insertuje jako invoker, nie SECURITY DEFINER
GRANT SELECT, INSERT        ON appdata.discovery_calls             TO n8n_crm_user;
GRANT SELECT, INSERT        ON appdata.transcripts                 TO n8n_crm_user;
GRANT SELECT, INSERT, UPDATE ON appdata.extractions                TO n8n_crm_user; -- UPDATE(accepted_by/accepted_at) w WF-4
GRANT SELECT, INSERT        ON appdata.participants                TO n8n_crm_user;
GRANT SELECT, INSERT        ON appdata.audits                      TO n8n_crm_user;
GRANT SELECT                ON appdata.audit_scores                TO n8n_crm_user;
GRANT SELECT, INSERT        ON appdata.recommendations             TO n8n_crm_user;
GRANT SELECT, INSERT        ON appdata.recommendation_goals        TO n8n_crm_user;
GRANT SELECT, INSERT        ON appdata.tasks                       TO n8n_crm_user;
GRANT SELECT, INSERT, UPDATE ON appdata.job_queue                  TO n8n_crm_user;

COMMIT;
