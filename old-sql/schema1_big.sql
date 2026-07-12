-- =============================================================
-- Workflow 1-10: full database schema (consolidated)
-- Single source of truth for the lead -> discovery -> audit ->
-- recommendation -> offer -> dispatch process.
--
-- Includes ALL columns added incrementally in seed1-seed4
-- (task_types.next_type_code, task_types.on_complete_hook,
--  participants.email), so a fresh install needs only:
--   1. this file
--   2. seed_workflow_config.sql ... seed4_workflow_config.sql (config rows)
--
-- Idempotent: safe to re-run on an existing database.
-- Run: psql "$DATABASE_URL" -f full_schema.sql
-- =============================================================

BEGIN;

-- ---------- Team & availability (used by n8n to pick an assignee) ----------

CREATE TABLE IF NOT EXISTS team_members (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name       TEXT NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    role            TEXT NOT NULL,                  -- e.g. 'sales', 'methodologist', 'auditor', 'admin'
    planka_user_id  TEXT,                           -- mapping to Planka user for card assignment
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS absences (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    member_id       BIGINT NOT NULL REFERENCES team_members(id),
    date_from       DATE NOT NULL,
    date_to         DATE NOT NULL,
    reason          TEXT,
    CHECK (date_to >= date_from)
);

-- ---------- Clients & contacts ----------

CREATE TABLE IF NOT EXISTS clients (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_type     TEXT NOT NULL DEFAULT 'unknown'
                    CHECK (client_type IN ('b2b', 'b2c', 'unknown')),
    company_name    TEXT,                           -- NULL for B2C individuals
    industry        TEXT,
    company_size    TEXT,
    lead_source     TEXT,                           -- form / bookings / email / phone / referral
    status          TEXT NOT NULL DEFAULT 'new'
                    CHECK (status IN ('new', 'active', 'won', 'lost', 'archived')),
    -- business context (stage 3 output; columns kept human-editable)
    communication_processes TEXT,
    key_roles       TEXT,
    business_impact TEXT,
    context_raw     JSONB,                          -- raw AI extraction, evolves freely
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS contacts (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id       BIGINT NOT NULL REFERENCES clients(id),
    full_name       TEXT NOT NULL,
    email           TEXT,
    phone           TEXT,
    position        TEXT,
    is_primary      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Opportunity (one sales process instance) ----------

CREATE TABLE IF NOT EXISTS opportunities (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id       BIGINT NOT NULL REFERENCES clients(id),
    owner_id        BIGINT REFERENCES team_members(id),      -- usually the salesperson
    flow_variant    TEXT NOT NULL DEFAULT 'default',          -- 'b2b', 'b2c', future variants
    stage           TEXT NOT NULL DEFAULT 'inquiry'
                    CHECK (stage IN (
                        'inquiry', 'discovery', 'analysis', 'audit_prep',
                        'audit', 'report', 'recommendation', 'offer_draft',
                        'offer_review', 'offer_sent', 'closed_won', 'closed_lost')),
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Process tasks (mirror of Planka cards; DB stays the truth) ----------

CREATE TABLE IF NOT EXISTS task_types (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code             TEXT UNIQUE NOT NULL,          -- e.g. 'paste_transcript', 'analyze_needs'
    name             TEXT NOT NULL,
    default_role     TEXT,                          -- role used by n8n to pick assignee
    planka_board_id  TEXT,
    planka_list_id   TEXT,                          -- list where new cards land
    form_url         TEXT,                          -- optional: validated form for rich stages
    next_type_code   TEXT,                          -- WF2 engine: next task in the chain (NULL = end/hook)
    on_complete_hook TEXT,                          -- WF2 engine: n8n webhook path called after completion
    description      TEXT
);

CREATE TABLE IF NOT EXISTS process_tasks (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    opportunity_id  BIGINT NOT NULL REFERENCES opportunities(id),
    task_type_id    BIGINT NOT NULL REFERENCES task_types(id),
    assignee_id     BIGINT REFERENCES team_members(id),
    planka_card_id  TEXT,                           -- set by n8n after card creation
    status          TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'in_progress', 'done', 'rejected', 'cancelled')),
    due_at          TIMESTAMPTZ,
    payload         JSONB,                          -- raw field values read back from Planka
    error_note      TEXT,                           -- set by n8n when validation fails
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
);

-- n8n reads this instead of hardcoded mappings: one place to evolve fields
CREATE TABLE IF NOT EXISTS field_mappings (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_type_id    BIGINT NOT NULL REFERENCES task_types(id),
    planka_field    TEXT NOT NULL,                  -- custom field name/id on the card
    target_table    TEXT NOT NULL,
    target_column   TEXT NOT NULL,
    is_required     BOOLEAN NOT NULL DEFAULT FALSE,
    transform       TEXT,                           -- optional hint: 'trim', 'to_int', 'to_number', 'date_pl'
    UNIQUE (task_type_id, planka_field)
);

-- ---------- Discovery ----------

CREATE TABLE IF NOT EXISTS discovery_calls (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    opportunity_id  BIGINT NOT NULL REFERENCES opportunities(id),
    meeting_date    DATE,
    attendees       TEXT,
    transcript      TEXT,                           -- pasted manually for now
    transcript_source TEXT DEFAULT 'manual'
                    CHECK (transcript_source IN ('manual', 'teams', 'external')),
    -- AI extraction (stage 3), human-corrected columns:
    client_goals    TEXT,
    challenges      TEXT,
    participant_types TEXT,
    decisions       TEXT,
    ai_extraction   JSONB,                          -- full raw AI output for audit/debug
    data_sufficient BOOLEAN,                        -- human decision: enough info to proceed?
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Participants & audits ----------

CREATE TABLE IF NOT EXISTS participants (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id       BIGINT NOT NULL REFERENCES clients(id),
    full_name       TEXT NOT NULL,
    email           TEXT,                           -- WF5 upsert key (unique per client)
    position        TEXT,
    self_assessed_level TEXT,                       -- CEFR from pre-audit form
    communication_situations TEXT,
    usage_frequency TEXT,
    manager_needs   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audits (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    opportunity_id  BIGINT NOT NULL REFERENCES opportunities(id),
    participant_id  BIGINT NOT NULL REFERENCES participants(id),
    auditor_id      BIGINT REFERENCES team_members(id),
    scope           JSONB,                          -- stage 4 output: what to examine
    audit_date      DATE,
    -- stage 5: human assessment (validated form, not free text on a card)
    language_level  TEXT CHECK (language_level IN
                    ('A1','A2','B1','B1+','B2','B2+','C1','C2')),
    vocabulary      SMALLINT CHECK (vocabulary BETWEEN 1 AND 5),
    accuracy        SMALLINT CHECK (accuracy BETWEEN 1 AND 5),
    fluency         SMALLINT CHECK (fluency BETWEEN 1 AND 5),
    communicativeness SMALLINT CHECK (communicativeness BETWEEN 1 AND 5),
    strengths       TEXT,
    gaps            TEXT,
    observations    TEXT,
    -- stage 6: report
    report_draft    TEXT,                           -- AI draft from template
    report_final    TEXT,
    report_status   TEXT NOT NULL DEFAULT 'pending'
                    CHECK (report_status IN ('pending', 'draft', 'approved')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Recommendation ----------

CREATE TABLE IF NOT EXISTS recommendations (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    opportunity_id  BIGINT NOT NULL REFERENCES opportunities(id),
    rec_type        TEXT NOT NULL CHECK (rec_type IN
                    ('business_english', 'english_plus_skills', 'skills_only', 'mixed')),
    justification_draft TEXT,                       -- AI draft
    justification_final TEXT,
    priority        TEXT,
    proposed_path   TEXT,
    hours           NUMERIC(6,1),
    training_variant TEXT,
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'approved', 'rejected')),
    approved_by     BIGINT REFERENCES team_members(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Offers (with full history) ----------

CREATE TABLE IF NOT EXISTS offers (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    opportunity_id  BIGINT NOT NULL REFERENCES opportunities(id),
    recommendation_id BIGINT REFERENCES recommendations(id),
    template_code   TEXT NOT NULL DEFAULT 'default',
    headcount       INT,
    hours           NUMERIC(6,1),
    price           NUMERIC(12,2),
    currency        TEXT NOT NULL DEFAULT 'PLN',
    training_variant TEXT,
    sections        JSONB,                          -- which sections/case studies/testimonials to include
    layout_overrides JSONB,                         -- salesperson's visual tweaks in the offer app
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'in_review', 'approved', 'sent', 'archived')),
    sent_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Immutable snapshots: every approval/send creates a version row (WF8, WF9, WF10)
CREATE TABLE IF NOT EXISTS offer_versions (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    offer_id        BIGINT NOT NULL REFERENCES offers(id),
    version_no      INT NOT NULL,
    snapshot        JSONB NOT NULL,                 -- full offer data at that moment
    file_url        TEXT,                           -- generated PDF/HTML export, if any
    created_by      BIGINT REFERENCES team_members(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (offer_id, version_no)
);

-- ---------- Indexes ----------

CREATE INDEX IF NOT EXISTS idx_opportunities_client   ON opportunities(client_id);
CREATE INDEX IF NOT EXISTS idx_tasks_opportunity      ON process_tasks(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee_status  ON process_tasks(assignee_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_planka_card      ON process_tasks(planka_card_id);
CREATE INDEX IF NOT EXISTS idx_audits_opportunity     ON audits(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_offers_opportunity     ON offers(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_participants_client    ON participants(client_id);
CREATE INDEX IF NOT EXISTS idx_contacts_client        ON contacts(client_id);

-- ---------- updated_at trigger ----------

CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Recreate triggers idempotently
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['clients','opportunities','audits','recommendations','offers']
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_touch_%I ON %I', t, t);
        EXECUTE format(
            'CREATE TRIGGER trg_touch_%I BEFORE UPDATE ON %I
             FOR EACH ROW EXECUTE FUNCTION touch_updated_at()', t, t);
    END LOOP;
END $$;

COMMIT;