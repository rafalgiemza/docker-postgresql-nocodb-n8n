-- ============================================================================
-- CoAction workflow database schema (v2)
-- Target: PostgreSQL 14+
-- Usage:  psql -U <user> -d coaction_db -f schema.sql
--
-- v2 changes (after legacy CRM analysis + flow revision):
--  * deals.status rewritten to the real flow, incl. post-offer stages
--    (offer_discussed, contract_sent) and 'disqualified' (MQL/SQL world)
--  * deals: + qualification (MQL/SQL), + disqualification_reason,
--    + estimated_value (pipeline forecasting)
--  * clients: + folder_url
--  * NEW table deal_status_history: replaces 11 milestone-date columns from
--    the legacy Excel with one append-only log (stage durations for free)
--  * meeting types clarified: demo = B2C meeting, audit = B2B meeting
--  * dropped: awaiting_data status (missing-data requests are handled as
--    tasks within 'adjustment', not as a deal status)
--
-- Design notes:
--  * Single source of truth for the lead -> signed contract process (stage 1).
--  * Status/type columns use TEXT + CHECK constraints instead of ENUM types,
--    so adding a new variant is a cheap ALTER (plays nicer with NocoDB).
--  * Offers are immutable: a correction = a new row with version + 1.
--    Only the status column may change after insert (enforced by trigger).
--  * Planka is a dumb UI: tasks table mirrors Planka cards so process
--    history lives in the database, not in the kanban tool.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- Helper: auto-update updated_at on every UPDATE
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ----------------------------------------------------------------------------
-- users: internal team members (Przemek, Dorota, Basia, Kasia) + n8n bot.
-- The bot account is used as 'actor' for automated changes and to filter out
-- self-inflicted Planka webhook events (anti-loop rule).
-- TODO: replace with employees + absences tables when substitution logic
--       is introduced; n8n assignee routing is hardcoded for now.
-- ----------------------------------------------------------------------------
CREATE TABLE users (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name       TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    role            TEXT NOT NULL
                    CHECK (role IN ('sales', 'methodologist_b2c', 'methodologist_b2b', 'reviewer', 'admin', 'bot')),
    planka_user_id  TEXT UNIQUE,          -- mapping to Planka account
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMENT ON TABLE users IS 'Internal team members + n8n bot; maps assignees/actors to Planka accounts';

-- ----------------------------------------------------------------------------
-- clients: the paying entity / main contact (company for B2B, person for B2C)
-- The contact person is NOT a participant by default (e.g. CEO buying for staff).
-- ----------------------------------------------------------------------------
CREATE TABLE clients (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    type                TEXT NOT NULL CHECK (type IN ('B2B', 'B2C')),
    company_name        TEXT,             -- NULL for B2C
    contact_first_name  TEXT NOT NULL,
    contact_last_name   TEXT,
    contact_email       TEXT NOT NULL,
    contact_phone       TEXT,
    industry            TEXT,             -- mainly B2B, filled from AI extraction
    company_size        TEXT,             -- mainly B2B
    lead_source         TEXT,             -- form / bookings / email / phone / referral...
    folder_url          TEXT,             -- link to the client folder (docs, materials)
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_b2b_has_company
        CHECK (type = 'B2C' OR company_name IS NOT NULL)
);

CREATE INDEX idx_clients_contact_email ON clients (contact_email);

CREATE TRIGGER trg_clients_updated_at
    BEFORE UPDATE ON clients
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMENT ON TABLE clients IS 'Paying entity / main contact; B2C duplicates person data with participants by design (kept simple on purpose)';

-- ----------------------------------------------------------------------------
-- deals: a single sales process for a client (client can have many over time,
-- e.g. "B2B continuation" creates a new deal for the same client)
--
-- Status flow (n8n enforces per-variant transition order, DB enforces values):
--   Both variants share one skeleton; only the assessment meeting differs:
--   B2C: new -> qualified -> discovery -> analysis -> recommendation (draft
--        offer v1) -> demo (draft presented + assessment) -> adjustment
--        -> offer_sent -> offer_discussed -> contract_sent -> won | lost
--   B2B: new -> qualified -> discovery -> analysis -> recommendation (draft
--        offer v1) -> audit (N assessment meetings) -> adjustment
--        -> offer_sent -> offer_discussed -> contract_sent -> won | lost
--   Any variant can branch to 'disqualified' (early) or 'lost' (late).
--   'adjustment' is optional (skipped when the draft needs no changes).
-- ----------------------------------------------------------------------------
CREATE TABLE deals (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id               BIGINT NOT NULL REFERENCES clients (id) ON DELETE RESTRICT,
    title                   TEXT NOT NULL,    -- human-readable label, set by n8n on creation
                                              -- (e.g. "Janusz Sp. z o.o. — B2B"); display value
                                              -- on NocoDB kanban cards and Planka cards
    variant                 TEXT NOT NULL
                            CHECK (variant IN ('B2C', 'B2B_pre_discovery', 'B2B_post_discovery', 'B2B_continuation', 'special')),
    qualification           TEXT
                            CHECK (qualification IN ('MQL', 'SQL')),
    status                  TEXT NOT NULL DEFAULT 'new'
                            CHECK (status IN (
                                'new',              -- lead registered
                                'qualified',        -- lead verified by sales (MQL/SQL set)
                                'disqualified',     -- rejected at qualification (terminal)
                                'discovery',        -- discovery call scheduled/done
                                'analysis',         -- transcript analysis + needs analysis
                                'audit',            -- B2B only: participant audits in progress
                                'recommendation',   -- recommendations = draft offer (v1)
                                'demo',             -- B2C only: demo meeting, draft presented
                                'adjustment',       -- post-demo/audit corrections, data completion
                                'offer_sent',       -- final offer sent to client
                                'offer_discussed',  -- offer discussed with client
                                'contract_sent',    -- contract sent
                                'won',              -- contract signed (terminal)
                                'lost'              -- opportunity lost (terminal)
                            )),
    estimated_value         NUMERIC(12, 2),   -- pipeline value estimate, before offer pricing
    disqualification_reason TEXT,             -- why the lead was rejected at qualification
    lost_reason             TEXT
                            CHECK (lost_reason IN ('budget', 'timing', 'competitor', 'no_response', 'other')),
    lost_note               TEXT,             -- free-text context, e.g. "budget cut in Q3, follow up in Q4"
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at               TIMESTAMPTZ,      -- set by n8n when status becomes won/lost/disqualified
    -- Guards: terminal negative statuses require a reason
    CONSTRAINT chk_lost_requires_reason
        CHECK (status <> 'lost' OR lost_reason IS NOT NULL),
    CONSTRAINT chk_disqualified_requires_reason
        CHECK (status <> 'disqualified' OR disqualification_reason IS NOT NULL)
);

CREATE INDEX idx_deals_client_id ON deals (client_id);
CREATE INDEX idx_deals_status ON deals (status);

CREATE TRIGGER trg_deals_updated_at
    BEFORE UPDATE ON deals
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMENT ON TABLE deals IS 'One sales process (stage 1: inquiry -> signed contract); backbone of the workflow';

-- ----------------------------------------------------------------------------
-- deal_status_history: append-only log of status changes, written by n8n.
-- Replaces the 11 milestone-date columns from the legacy Excel CRM and gives
-- stage-duration reporting for free. Never UPDATE/DELETE rows here.
-- ----------------------------------------------------------------------------
CREATE TABLE deal_status_history (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deal_id         BIGINT NOT NULL REFERENCES deals (id) ON DELETE RESTRICT,
    status          TEXT NOT NULL,        -- value deals.status changed TO
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    changed_by      BIGINT REFERENCES users (id)  -- human actor or the n8n bot
);

CREATE INDEX idx_deal_status_history_deal_id ON deal_status_history (deal_id, changed_at);

COMMENT ON TABLE deal_status_history IS 'Append-only status log; source for milestone dates and stage-duration reports';

-- ----------------------------------------------------------------------------
-- participants: people who will actually be trained/audited.
-- Linked to CLIENT (not deal) so the same person survives into a continuation deal.
-- ----------------------------------------------------------------------------
CREATE TABLE participants (
    id                          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id                   BIGINT NOT NULL REFERENCES clients (id) ON DELETE RESTRICT,
    first_name                  TEXT NOT NULL,
    last_name                   TEXT,
    email                       TEXT,
    position                    TEXT,             -- job title / role in the company
    self_assessed_level         TEXT,             -- e.g. A2/B1... from pre-audit form
    communication_situations    TEXT,             -- typical situations (calls, presentations...)
    communication_frequency     TEXT,             -- how often English is used
    manager_needs               TEXT,             -- needs reported by manager / HR
    source                      TEXT NOT NULL DEFAULT 'manual'
                                CHECK (source IN ('manual', 'form', 'ai_extraction')),
    verification_status         TEXT NOT NULL DEFAULT 'verified'
                                CHECK (verification_status IN ('draft', 'verified')),
                                -- 'draft' when created by AI from transcript, human verifies
    notes                       TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_participants_client_id ON participants (client_id);

CREATE TRIGGER trg_participants_updated_at
    BEFORE UPDATE ON participants
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMENT ON TABLE participants IS 'Trainees/auditees; FK to client (not deal) so people persist across continuation deals';

-- ----------------------------------------------------------------------------
-- meetings: typed meetings, each type gets its own n8n flow.
--   discovery - initial call with the contact person (B2B and B2C)
--   demo      - B2C meeting: draft offer presented + participant assessed
--   audit     - B2B meeting: participant assessment (a deal can have many)
-- Future types (lesson_1..N for delivery phase) = one ALTER on this CHECK.
-- Raw AI extraction lives here; the approved/curated version is a human
-- decision propagated by n8n.
-- ----------------------------------------------------------------------------
CREATE TABLE meetings (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deal_id             BIGINT NOT NULL REFERENCES deals (id) ON DELETE RESTRICT,
    type                TEXT NOT NULL CHECK (type IN ('discovery', 'demo', 'audit')),
    scheduled_at        TIMESTAMPTZ,
    booking_ref         TEXT,             -- external id from Bookings, for idempotent webhooks
    attendees           TEXT,             -- free text; formal links live in audit_results
    transcript          TEXT,
    transcript_status   TEXT NOT NULL DEFAULT 'missing'
                        CHECK (transcript_status IN ('missing', 'pasted', 'approved')),
    ai_extraction       JSONB,            -- raw LLM output: goals, challenges, business context,
                                          -- participant candidates, communication situations
    notes               TEXT,             -- human corrections / info not present in the recording
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_meetings_booking_ref ON meetings (booking_ref) WHERE booking_ref IS NOT NULL;
CREATE INDEX idx_meetings_deal_id ON meetings (deal_id);

CREATE TRIGGER trg_meetings_updated_at
    BEFORE UPDATE ON meetings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMENT ON TABLE meetings IS 'Typed meetings: discovery (all), demo (B2C), audit (B2B, many per deal); one n8n flow per type';

-- ----------------------------------------------------------------------------
-- audit_results: evaluation of ONE participant in ONE meeting.
-- For B2C the evaluating meeting is the demo; for B2B it is an audit.
-- One meeting can evaluate several people; one person can be evaluated
-- in several meetings (e.g. a follow-up audit) -- hence the junction design.
-- ----------------------------------------------------------------------------
CREATE TABLE audit_results (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    meeting_id          BIGINT NOT NULL REFERENCES meetings (id) ON DELETE RESTRICT,
    participant_id      BIGINT NOT NULL REFERENCES participants (id) ON DELETE RESTRICT,
    evaluated_by        BIGINT REFERENCES users (id),
    language_level      TEXT,             -- CEFR level assessed by methodologist
    vocabulary          TEXT,
    grammar_accuracy    TEXT,
    fluency             TEXT,
    communicativeness   TEXT,
    strengths           TEXT,
    gaps                TEXT,
    skill_needs         TEXT,
    observations        TEXT,             -- free-form auditor notes
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_audit_per_meeting_participant UNIQUE (meeting_id, participant_id)
);

CREATE INDEX idx_audit_results_participant_id ON audit_results (participant_id);

CREATE TRIGGER trg_audit_results_updated_at
    BEFORE UPDATE ON audit_results
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMENT ON TABLE audit_results IS 'Merit evaluation: one row = one participant evaluated in one meeting (demo for B2C, audit for B2B)';

-- ----------------------------------------------------------------------------
-- recommendations: always per participant (B2B and B2C alike).
-- Double FK (participant + deal) is intentional light denormalization:
-- participant links to client, so deal_id disambiguates which sales process
-- this recommendation belongs to (continuation deals!).
-- ----------------------------------------------------------------------------
CREATE TABLE recommendations (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    participant_id      BIGINT NOT NULL REFERENCES participants (id) ON DELETE RESTRICT,
    deal_id             BIGINT NOT NULL REFERENCES deals (id) ON DELETE RESTRICT,
    recommended_by      BIGINT REFERENCES users (id),
    path_type           TEXT NOT NULL
                        CHECK (path_type IN ('business_english', 'english_plus_skills', 'skills_only', 'mixed')),
    justification       TEXT,
    priority            TEXT CHECK (priority IN ('high', 'medium', 'low')),
    proposed_hours      INTEGER CHECK (proposed_hours > 0),
    training_variant    TEXT,             -- individual / group / intensive... free text for now
    status              TEXT NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft', 'approved', 'dropped')),
                        -- 'dropped' = valid recommendation excluded from the final offer (e.g. budget cut)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_recommendations_deal_id ON recommendations (deal_id);
CREATE INDEX idx_recommendations_participant_id ON recommendations (participant_id);

CREATE TRIGGER trg_recommendations_updated_at
    BEFORE UPDATE ON recommendations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMENT ON TABLE recommendations IS 'Training path per participant per deal; the set of approved rows IS the draft offer content';

-- ----------------------------------------------------------------------------
-- offers: IMMUTABLE versions. A correction = INSERT with version + 1.
-- v1 with status 'draft' is the sketch presented at the demo (B2C) or after
-- audits (B2B); adjustments produce v2, v3... The previous version becomes
-- 'superseded'. recommendations_snapshot freezes the exact data, immune to
-- later edits of recommendation rows.
-- Only `status` may be updated after insert (enforced by trigger below).
-- NOTE: when adding a column to this table, add it to the trigger's column
-- list as well, otherwise the new column will be silently mutable.
-- ----------------------------------------------------------------------------
CREATE TABLE offers (
    id                          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deal_id                     BIGINT NOT NULL REFERENCES deals (id) ON DELETE RESTRICT,
    version                     INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    template_name               TEXT,
    total_hours                 INTEGER,
    price_net                   NUMERIC(12, 2),
    currency                    TEXT NOT NULL DEFAULT 'PLN',
    recommendations_snapshot    JSONB NOT NULL,   -- full frozen copies of included recommendations
    included_sections           JSONB,            -- case studies / testimonials / custom sections used
    file_url                    TEXT,             -- link to the generated document/presentation
    status                      TEXT NOT NULL DEFAULT 'draft'
                                CHECK (status IN ('draft', 'in_review', 'approved', 'sent', 'accepted', 'rejected', 'superseded')),
    created_by                  BIGINT REFERENCES users (id),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_offer_deal_version UNIQUE (deal_id, version)
);

CREATE INDEX idx_offers_deal_id ON offers (deal_id);

-- Immutability guard: after insert, only status (and updated_at) may change
CREATE OR REPLACE FUNCTION enforce_offer_immutability()
RETURNS trigger AS $$
BEGIN
    IF (NEW.deal_id, NEW.version, NEW.template_name, NEW.total_hours,
        NEW.price_net, NEW.currency, NEW.recommendations_snapshot,
        NEW.included_sections, NEW.file_url, NEW.created_by, NEW.created_at)
       IS DISTINCT FROM
       (OLD.deal_id, OLD.version, OLD.template_name, OLD.total_hours,
        OLD.price_net, OLD.currency, OLD.recommendations_snapshot,
        OLD.included_sections, OLD.file_url, OLD.created_by, OLD.created_at)
    THEN
        RAISE EXCEPTION 'Offers are immutable: create a new version instead of editing (offer id=%)', OLD.id;
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_offers_immutable
    BEFORE UPDATE ON offers
    FOR EACH ROW EXECUTE FUNCTION enforce_offer_immutability();

COMMENT ON TABLE offers IS 'Immutable offer versions; v1 draft = sketch presented to the client, correction = new row, only status is mutable';

-- ----------------------------------------------------------------------------
-- tasks: mirror of Planka cards. Planka is disposable UI; process history,
-- durations and reporting live here. tasks.stage mirrors deals.status values.
-- ----------------------------------------------------------------------------
CREATE TABLE tasks (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deal_id             BIGINT NOT NULL REFERENCES deals (id) ON DELETE RESTRICT,
    planka_card_id      TEXT UNIQUE,      -- NULL until the card is created in Planka
    stage               TEXT NOT NULL,    -- process stage this task belongs to (mirrors deals.status values)
    task_type           TEXT NOT NULL,    -- machine key for the n8n state machine, e.g. 'verify_lead',
                                          -- 'paste_transcript_discovery', 'confirm_audits_complete'
    title               TEXT NOT NULL,
    assignee_id         BIGINT REFERENCES users (id),
    status              TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open', 'in_progress', 'done', 'cancelled')),
    due_at              TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_tasks_deal_id ON tasks (deal_id);
CREATE INDEX idx_tasks_assignee_status ON tasks (assignee_id, status);

CREATE TRIGGER trg_tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMENT ON TABLE tasks IS 'Mirror of Planka cards; task_type drives the n8n state machine, stage duration reporting lives here';

COMMIT;