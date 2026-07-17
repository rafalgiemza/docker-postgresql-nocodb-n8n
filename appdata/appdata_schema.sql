--
-- PostgreSQL database dump
--

\restrict TZchxPdxenEy9ZVRCkzxPEIfegdmtu7ROclHQncrwmKlhZePWdycVIvDQ3Eo8Uq

-- Dumped from database version 16.14 (Debian 16.14-1.pgdg13+1)
-- Dumped by pg_dump version 16.14 (Debian 16.14-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: appdata; Type: SCHEMA; Schema: -; Owner: appdata_owner
--

CREATE SCHEMA appdata;


ALTER SCHEMA appdata OWNER TO appdata_owner;

--
-- Name: crm; Type: SCHEMA; Schema: -; Owner: appdata_owner
--

CREATE SCHEMA crm;


ALTER SCHEMA crm OWNER TO appdata_owner;

--
-- Name: citext; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA appdata;


--
-- Name: EXTENSION citext; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION citext IS 'data type for case-insensitive character strings';


--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA appdata;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: client_type; Type: TYPE; Schema: appdata; Owner: appdata_owner
--

CREATE TYPE appdata.client_type AS ENUM (
    'B2B',
    'B2C'
);


ALTER TYPE appdata.client_type OWNER TO appdata_owner;

--
-- Name: contact_form; Type: TYPE; Schema: appdata; Owner: appdata_owner
--

CREATE TYPE appdata.contact_form AS ENUM (
    'booking',
    'email',
    'phone',
    'form',
    'walk_in'
);


ALTER TYPE appdata.contact_form OWNER TO appdata_owner;

--
-- Name: job_status; Type: TYPE; Schema: appdata; Owner: appdata_owner
--

CREATE TYPE appdata.job_status AS ENUM (
    'queued',
    'running',
    'done',
    'failed'
);


ALTER TYPE appdata.job_status OWNER TO appdata_owner;

--
-- Name: lead_qualif; Type: TYPE; Schema: appdata; Owner: appdata_owner
--

CREATE TYPE appdata.lead_qualif AS ENUM (
    'MQL',
    'SQL',
    'DISQUALIFIED',
    'UNQUALIFIED'
);


ALTER TYPE appdata.lead_qualif OWNER TO appdata_owner;

--
-- Name: lead_source; Type: TYPE; Schema: appdata; Owner: appdata_owner
--

CREATE TYPE appdata.lead_source AS ENUM (
    'google',
    'referral',
    'linkedin',
    'website',
    'inbound_call',
    'partner',
    'other'
);


ALTER TYPE appdata.lead_source OWNER TO appdata_owner;

--
-- Name: lesson_format; Type: TYPE; Schema: appdata; Owner: appdata_owner
--

CREATE TYPE appdata.lesson_format AS ENUM (
    '1-1',
    'pair',
    'group'
);


ALTER TYPE appdata.lesson_format OWNER TO appdata_owner;

--
-- Name: offer_status; Type: TYPE; Schema: appdata; Owner: appdata_owner
--

CREATE TYPE appdata.offer_status AS ENUM (
    'draft',
    'ready',
    'sent',
    'accepted',
    'rejected',
    'superseded'
);


ALTER TYPE appdata.offer_status OWNER TO appdata_owner;

--
-- Name: opp_stage; Type: TYPE; Schema: appdata; Owner: appdata_owner
--

CREATE TYPE appdata.opp_stage AS ENUM (
    'nowa',
    'badanie_potrzeb',
    'demo',
    'przygotowanie_oferty',
    'oferta_wyslana',
    'omowienie_oferty',
    'umowa_wyslana',
    'umowa_podpisana',
    'utracona',
    'archiwum'
);


ALTER TYPE appdata.opp_stage OWNER TO appdata_owner;

--
-- Name: opp_state; Type: TYPE; Schema: appdata; Owner: appdata_owner
--

CREATE TYPE appdata.opp_state AS ENUM (
    'otwarta',
    'zamknieta',
    'wstrzymana'
);


ALTER TYPE appdata.opp_state OWNER TO appdata_owner;

--
-- Name: rec_type; Type: TYPE; Schema: appdata; Owner: appdata_owner
--

CREATE TYPE appdata.rec_type AS ENUM (
    'business_english',
    'english_for_it',
    'english_plus_skills',
    'skills_only',
    'mixed'
);


ALTER TYPE appdata.rec_type OWNER TO appdata_owner;

--
-- Name: task_status; Type: TYPE; Schema: appdata; Owner: appdata_owner
--

CREATE TYPE appdata.task_status AS ENUM (
    'todo',
    'in_progress',
    'blocked',
    'done',
    'cancelled'
);


ALTER TYPE appdata.task_status OWNER TO appdata_owner;

--
-- Name: transcript_src; Type: TYPE; Schema: appdata; Owner: appdata_owner
--

CREATE TYPE appdata.transcript_src AS ENUM (
    'manual_paste',
    'asr_auto',
    'upload_file'
);


ALTER TYPE appdata.transcript_src OWNER TO appdata_owner;

--
-- Name: log_opportunity_stage_change(); Type: FUNCTION; Schema: appdata; Owner: appdata_owner
--

CREATE FUNCTION appdata.log_opportunity_stage_change() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    INSERT INTO appdata.opportunity_stage_history (opportunity_id, from_stage, to_stage, changed_by)
    VALUES (NEW.id, OLD.stage, NEW.stage, NULL);
    RETURN NEW;
END;
$$;


ALTER FUNCTION appdata.log_opportunity_stage_change() OWNER TO appdata_owner;

--
-- Name: recalc_offer_totals(bigint); Type: FUNCTION; Schema: appdata; Owner: appdata_owner
--

CREATE FUNCTION appdata.recalc_offer_totals(p_offer_id bigint) RETURNS void
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


ALTER FUNCTION appdata.recalc_offer_totals(p_offer_id bigint) OWNER TO appdata_owner;

--
-- Name: set_offer_item_unit_price(); Type: FUNCTION; Schema: appdata; Owner: appdata_owner
--

CREATE FUNCTION appdata.set_offer_item_unit_price() RETURNS trigger
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


ALTER FUNCTION appdata.set_offer_item_unit_price() OWNER TO appdata_owner;

--
-- Name: set_updated_at(); Type: FUNCTION; Schema: appdata; Owner: appdata_owner
--

CREATE FUNCTION appdata.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;


ALTER FUNCTION appdata.set_updated_at() OWNER TO appdata_owner;

--
-- Name: trg_offer_items_recalc_totals_fn(); Type: FUNCTION; Schema: appdata; Owner: appdata_owner
--

CREATE FUNCTION appdata.trg_offer_items_recalc_totals_fn() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    PERFORM appdata.recalc_offer_totals(COALESCE(NEW.offer_id, OLD.offer_id));
    RETURN NULL;
END;
$$;


ALTER FUNCTION appdata.trg_offer_items_recalc_totals_fn() OWNER TO appdata_owner;

--
-- Name: trg_offers_recalc_on_discount_fn(); Type: FUNCTION; Schema: appdata; Owner: appdata_owner
--

CREATE FUNCTION appdata.trg_offers_recalc_on_discount_fn() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    PERFORM appdata.recalc_offer_totals(NEW.id);
    RETURN NULL;
END;
$$;


ALTER FUNCTION appdata.trg_offers_recalc_on_discount_fn() OWNER TO appdata_owner;

--
-- Name: v_audit_scores_instead_of_update(); Type: FUNCTION; Schema: crm; Owner: appdata_owner
--

CREATE FUNCTION crm.v_audit_scores_instead_of_update() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'appdata', 'crm', 'pg_temp'
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


ALTER FUNCTION crm.v_audit_scores_instead_of_update() OWNER TO appdata_owner;

--
-- Name: v_offer_builder_instead_of_update(); Type: FUNCTION; Schema: crm; Owner: appdata_owner
--

CREATE FUNCTION crm.v_offer_builder_instead_of_update() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'appdata', 'crm', 'pg_temp'
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


ALTER FUNCTION crm.v_offer_builder_instead_of_update() OWNER TO appdata_owner;

--
-- Name: v_offer_goals_instead_of(); Type: FUNCTION; Schema: crm; Owner: appdata_owner
--

CREATE FUNCTION crm.v_offer_goals_instead_of() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'appdata', 'crm', 'pg_temp'
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


ALTER FUNCTION crm.v_offer_goals_instead_of() OWNER TO appdata_owner;

--
-- Name: v_pipeline_instead_of_update(); Type: FUNCTION; Schema: crm; Owner: appdata_owner
--

CREATE FUNCTION crm.v_pipeline_instead_of_update() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'appdata', 'crm', 'pg_temp'
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


ALTER FUNCTION crm.v_pipeline_instead_of_update() OWNER TO appdata_owner;

--
-- Name: v_tasks_instead_of_update(); Type: FUNCTION; Schema: crm; Owner: appdata_owner
--

CREATE FUNCTION crm.v_tasks_instead_of_update() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'appdata', 'crm', 'pg_temp'
    AS $$
BEGIN
    UPDATE appdata.tasks
    SET status       = NEW.status,
        completed_at = CASE WHEN NEW.status = 'done' THEN now() ELSE completed_at END
    WHERE id = NEW.task_id;
    RETURN NEW;
END;
$$;


ALTER FUNCTION crm.v_tasks_instead_of_update() OWNER TO appdata_owner;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: audit_scores; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.audit_scores (
    id bigint NOT NULL,
    audit_id bigint NOT NULL,
    dimension text NOT NULL,
    cefr_level text NOT NULL,
    cefr_decimal numeric(2,1) DEFAULT 0 NOT NULL,
    cefr_numeric numeric GENERATED ALWAYS AS ((
CASE cefr_level
    WHEN 'A1'::text THEN 1.0
    WHEN 'A2'::text THEN 2.0
    WHEN 'B1'::text THEN 3.0
    WHEN 'B2'::text THEN 4.0
    WHEN 'C1'::text THEN 5.0
    WHEN 'C2'::text THEN 6.0
    ELSE NULL::numeric
END + cefr_decimal)) STORED,
    justification text,
    CONSTRAINT audit_scores_cefr_decimal_check CHECK (((cefr_decimal >= (0)::numeric) AND (cefr_decimal < (1)::numeric))),
    CONSTRAINT audit_scores_cefr_level_check CHECK ((cefr_level = ANY (ARRAY['A1'::text, 'A2'::text, 'B1'::text, 'B2'::text, 'C1'::text, 'C2'::text]))),
    CONSTRAINT audit_scores_dimension_check CHECK ((dimension = ANY (ARRAY['overall'::text, 'range'::text, 'accuracy'::text, 'fluency'::text, 'communicativeness'::text])))
);


ALTER TABLE appdata.audit_scores OWNER TO appdata_owner;

--
-- Name: audit_scores_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.audit_scores_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.audit_scores_id_seq OWNER TO appdata_owner;

--
-- Name: audit_scores_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.audit_scores_id_seq OWNED BY appdata.audit_scores.id;


--
-- Name: audits; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.audits (
    id bigint NOT NULL,
    participant_id bigint NOT NULL,
    opportunity_id bigint NOT NULL,
    auditor_user_id bigint,
    conducted_at timestamp with time zone,
    observations text,
    strengths text[],
    gaps text[],
    scope jsonb,
    status text DEFAULT 'planned'::text NOT NULL,
    CONSTRAINT audits_status_check CHECK ((status = ANY (ARRAY['planned'::text, 'done'::text])))
);


ALTER TABLE appdata.audits OWNER TO appdata_owner;

--
-- Name: audits_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.audits_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.audits_id_seq OWNER TO appdata_owner;

--
-- Name: audits_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.audits_id_seq OWNED BY appdata.audits.id;


--
-- Name: clients; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.clients (
    id bigint NOT NULL,
    type appdata.client_type NOT NULL,
    organization_id bigint,
    primary_contact_id bigint,
    owner_user_id bigint,
    source appdata.lead_source,
    contact_form appdata.contact_form,
    qualification appdata.lead_qualif,
    disqualification_reason text,
    minio_prefix text,
    inbound_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE appdata.clients OWNER TO appdata_owner;

--
-- Name: clients_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.clients_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.clients_id_seq OWNER TO appdata_owner;

--
-- Name: clients_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.clients_id_seq OWNED BY appdata.clients.id;


--
-- Name: discovery_calls; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.discovery_calls (
    id bigint NOT NULL,
    opportunity_id bigint NOT NULL,
    scheduled_at timestamp with time zone,
    ended_at timestamp with time zone,
    duration_min integer,
    external_event_id text,
    meeting_url text,
    attendees jsonb
);


ALTER TABLE appdata.discovery_calls OWNER TO appdata_owner;

--
-- Name: discovery_calls_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.discovery_calls_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.discovery_calls_id_seq OWNER TO appdata_owner;

--
-- Name: discovery_calls_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.discovery_calls_id_seq OWNED BY appdata.discovery_calls.id;


--
-- Name: extractions; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.extractions (
    id bigint NOT NULL,
    transcript_id bigint NOT NULL,
    model text,
    prompt_version text,
    payload jsonb NOT NULL,
    accepted_by bigint,
    accepted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE appdata.extractions OWNER TO appdata_owner;

--
-- Name: extractions_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.extractions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.extractions_id_seq OWNER TO appdata_owner;

--
-- Name: extractions_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.extractions_id_seq OWNED BY appdata.extractions.id;


--
-- Name: files; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.files (
    id bigint NOT NULL,
    bucket text NOT NULL,
    key text NOT NULL,
    mime text,
    size_bytes bigint,
    sha256 text,
    uploaded_by bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE appdata.files OWNER TO appdata_owner;

--
-- Name: files_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.files_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.files_id_seq OWNER TO appdata_owner;

--
-- Name: files_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.files_id_seq OWNED BY appdata.files.id;


--
-- Name: job_queue; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.job_queue (
    id bigint NOT NULL,
    kind text NOT NULL,
    priority integer DEFAULT 1 NOT NULL,
    payload jsonb,
    status appdata.job_status DEFAULT 'queued'::appdata.job_status NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    last_error text,
    locked_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE appdata.job_queue OWNER TO appdata_owner;

--
-- Name: job_queue_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.job_queue_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.job_queue_id_seq OWNER TO appdata_owner;

--
-- Name: job_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.job_queue_id_seq OWNED BY appdata.job_queue.id;


--
-- Name: offer_items; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.offer_items (
    id bigint NOT NULL,
    offer_id bigint NOT NULL,
    "position" integer NOT NULL,
    product text,
    label text,
    hours integer,
    format appdata.lesson_format,
    pricing_tier_id bigint,
    unit_price_pln numeric(10,2)
);


ALTER TABLE appdata.offer_items OWNER TO appdata_owner;

--
-- Name: offer_items_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.offer_items_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.offer_items_id_seq OWNER TO appdata_owner;

--
-- Name: offer_items_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.offer_items_id_seq OWNED BY appdata.offer_items.id;


--
-- Name: offer_snapshots; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.offer_snapshots (
    id bigint NOT NULL,
    offer_id bigint NOT NULL,
    version integer NOT NULL,
    format text,
    minio_key text,
    sha256 text,
    payload_snapshot jsonb,
    template_id bigint,
    template_version integer,
    status appdata.job_status DEFAULT 'queued'::appdata.job_status NOT NULL,
    error text,
    generated_at timestamp with time zone,
    CONSTRAINT offer_snapshots_format_check CHECK ((format = ANY (ARRAY['pptx'::text, 'pdf'::text])))
);


ALTER TABLE appdata.offer_snapshots OWNER TO appdata_owner;

--
-- Name: offer_snapshots_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.offer_snapshots_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.offer_snapshots_id_seq OWNER TO appdata_owner;

--
-- Name: offer_snapshots_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.offer_snapshots_id_seq OWNED BY appdata.offer_snapshots.id;


--
-- Name: offer_templates; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.offer_templates (
    id bigint NOT NULL,
    name text NOT NULL,
    variant text,
    minio_key text,
    version integer DEFAULT 1 NOT NULL,
    placeholder_manifest jsonb,
    slide_map jsonb,
    active boolean DEFAULT true NOT NULL,
    uploaded_by bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT offer_templates_variant_check CHECK ((variant = ANY (ARRAY['b2c'::text, 'b2b'::text, 'continuation'::text, 'special'::text])))
);


ALTER TABLE appdata.offer_templates OWNER TO appdata_owner;

--
-- Name: offer_templates_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.offer_templates_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.offer_templates_id_seq OWNER TO appdata_owner;

--
-- Name: offer_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.offer_templates_id_seq OWNED BY appdata.offer_templates.id;


--
-- Name: offers; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.offers (
    id bigint NOT NULL,
    opportunity_id bigint NOT NULL,
    recommendation_id bigint,
    template_id bigint,
    version integer DEFAULT 1 NOT NULL,
    status appdata.offer_status DEFAULT 'draft'::appdata.offer_status NOT NULL,
    total_hours integer DEFAULT 0 NOT NULL,
    total_price_pln numeric(10,2) DEFAULT 0 NOT NULL,
    discount_pct numeric(4,2) DEFAULT 0 NOT NULL,
    valid_until date,
    included_testimonial_ids bigint[],
    included_sections text[],
    custom_notes text,
    created_by bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE appdata.offers OWNER TO appdata_owner;

--
-- Name: offers_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.offers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.offers_id_seq OWNER TO appdata_owner;

--
-- Name: offers_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.offers_id_seq OWNED BY appdata.offers.id;


--
-- Name: opportunities; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.opportunities (
    id bigint NOT NULL,
    client_id bigint NOT NULL,
    stage appdata.opp_stage DEFAULT 'nowa'::appdata.opp_stage NOT NULL,
    state appdata.opp_state DEFAULT 'otwarta'::appdata.opp_state NOT NULL,
    value_pln numeric(10,2),
    label text,
    next_action_at date,
    next_action text,
    loss_reason text,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE appdata.opportunities OWNER TO appdata_owner;

--
-- Name: opportunities_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.opportunities_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.opportunities_id_seq OWNER TO appdata_owner;

--
-- Name: opportunities_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.opportunities_id_seq OWNED BY appdata.opportunities.id;


--
-- Name: opportunity_stage_history; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.opportunity_stage_history (
    id bigint NOT NULL,
    opportunity_id bigint NOT NULL,
    from_stage appdata.opp_stage,
    to_stage appdata.opp_stage NOT NULL,
    changed_by bigint,
    changed_at timestamp with time zone DEFAULT now() NOT NULL,
    note text
);


ALTER TABLE appdata.opportunity_stage_history OWNER TO appdata_owner;

--
-- Name: opportunity_stage_history_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.opportunity_stage_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.opportunity_stage_history_id_seq OWNER TO appdata_owner;

--
-- Name: opportunity_stage_history_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.opportunity_stage_history_id_seq OWNED BY appdata.opportunity_stage_history.id;


--
-- Name: organizations; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.organizations (
    id bigint NOT NULL,
    name text NOT NULL,
    industry text,
    size_bucket text,
    nip text,
    business_context jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT organizations_size_bucket_check CHECK ((size_bucket = ANY (ARRAY['<50'::text, '50-250'::text, '250+'::text])))
);


ALTER TABLE appdata.organizations OWNER TO appdata_owner;

--
-- Name: organizations_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.organizations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.organizations_id_seq OWNER TO appdata_owner;

--
-- Name: organizations_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.organizations_id_seq OWNED BY appdata.organizations.id;


--
-- Name: participants; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.participants (
    id bigint NOT NULL,
    client_id bigint NOT NULL,
    person_id bigint,
    manager_needs text,
    self_assessment jsonb,
    communication_situations text[]
);


ALTER TABLE appdata.participants OWNER TO appdata_owner;

--
-- Name: participants_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.participants_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.participants_id_seq OWNER TO appdata_owner;

--
-- Name: participants_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.participants_id_seq OWNED BY appdata.participants.id;


--
-- Name: people; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.people (
    id bigint NOT NULL,
    organization_id bigint,
    first_name text,
    last_name text,
    email appdata.citext,
    phone text,
    job_title text,
    linkedin_url text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE appdata.people OWNER TO appdata_owner;

--
-- Name: people_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.people_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.people_id_seq OWNER TO appdata_owner;

--
-- Name: people_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.people_id_seq OWNED BY appdata.people.id;


--
-- Name: pricing_tiers; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.pricing_tiers (
    id bigint NOT NULL,
    product text NOT NULL,
    hours integer NOT NULL,
    format appdata.lesson_format NOT NULL,
    price_pln numeric(10,2) NOT NULL,
    valid_from date NOT NULL,
    valid_to date,
    CONSTRAINT pricing_tiers_hours_check CHECK ((hours > 0))
);


ALTER TABLE appdata.pricing_tiers OWNER TO appdata_owner;

--
-- Name: pricing_tiers_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.pricing_tiers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.pricing_tiers_id_seq OWNER TO appdata_owner;

--
-- Name: pricing_tiers_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.pricing_tiers_id_seq OWNED BY appdata.pricing_tiers.id;


--
-- Name: recommendation_goals; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.recommendation_goals (
    id bigint NOT NULL,
    recommendation_id bigint NOT NULL,
    "position" integer NOT NULL,
    title text,
    body text,
    stage_label text
);


ALTER TABLE appdata.recommendation_goals OWNER TO appdata_owner;

--
-- Name: recommendation_goals_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.recommendation_goals_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.recommendation_goals_id_seq OWNER TO appdata_owner;

--
-- Name: recommendation_goals_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.recommendation_goals_id_seq OWNED BY appdata.recommendation_goals.id;


--
-- Name: recommendations; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.recommendations (
    id bigint NOT NULL,
    opportunity_id bigint NOT NULL,
    audit_id bigint,
    type appdata.rec_type,
    headline text,
    situation_description text,
    rationale text,
    priority integer,
    approved_by bigint,
    approved_at timestamp with time zone
);


ALTER TABLE appdata.recommendations OWNER TO appdata_owner;

--
-- Name: recommendations_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.recommendations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.recommendations_id_seq OWNER TO appdata_owner;

--
-- Name: recommendations_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.recommendations_id_seq OWNED BY appdata.recommendations.id;


--
-- Name: tasks; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.tasks (
    id bigint NOT NULL,
    entity_type text NOT NULL,
    entity_id bigint NOT NULL,
    assignee_user_id bigint,
    title text NOT NULL,
    stage_ref appdata.opp_stage,
    status appdata.task_status DEFAULT 'todo'::appdata.task_status NOT NULL,
    due_at timestamp with time zone,
    payload jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    CONSTRAINT tasks_entity_type_check CHECK ((entity_type = ANY (ARRAY['opportunity'::text, 'audit'::text, 'offer'::text, 'transcript'::text])))
);


ALTER TABLE appdata.tasks OWNER TO appdata_owner;

--
-- Name: tasks_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.tasks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.tasks_id_seq OWNER TO appdata_owner;

--
-- Name: tasks_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.tasks_id_seq OWNED BY appdata.tasks.id;


--
-- Name: testimonials; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.testimonials (
    id bigint NOT NULL,
    author text NOT NULL,
    role text,
    quote text,
    tags text[],
    slide_template_idx integer,
    active boolean DEFAULT true NOT NULL
);


ALTER TABLE appdata.testimonials OWNER TO appdata_owner;

--
-- Name: testimonials_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.testimonials_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.testimonials_id_seq OWNER TO appdata_owner;

--
-- Name: testimonials_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.testimonials_id_seq OWNED BY appdata.testimonials.id;


--
-- Name: transcripts; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.transcripts (
    id bigint NOT NULL,
    discovery_call_id bigint,
    audit_id bigint,
    source appdata.transcript_src NOT NULL,
    language text[],
    raw_text text,
    curated_text text,
    recording_file_id bigint,
    search_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, COALESCE(curated_text, raw_text, ''::text))) STORED,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE appdata.transcripts OWNER TO appdata_owner;

--
-- Name: transcripts_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.transcripts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.transcripts_id_seq OWNER TO appdata_owner;

--
-- Name: transcripts_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.transcripts_id_seq OWNED BY appdata.transcripts.id;


--
-- Name: users; Type: TABLE; Schema: appdata; Owner: appdata_owner
--

CREATE TABLE appdata.users (
    id bigint NOT NULL,
    full_name text NOT NULL,
    email appdata.citext NOT NULL,
    role text NOT NULL,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT users_role_check CHECK ((role = ANY (ARRAY['sales'::text, 'auditor'::text, 'methodologist'::text, 'admin'::text, 'bot'::text])))
);


ALTER TABLE appdata.users OWNER TO appdata_owner;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: appdata; Owner: appdata_owner
--

CREATE SEQUENCE appdata.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE appdata.users_id_seq OWNER TO appdata_owner;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: appdata; Owner: appdata_owner
--

ALTER SEQUENCE appdata.users_id_seq OWNED BY appdata.users.id;


--
-- Name: v_audit_scores; Type: VIEW; Schema: crm; Owner: appdata_owner
--

CREATE VIEW crm.v_audit_scores AS
 SELECT s.id AS score_id,
    s.audit_id,
    s.dimension,
    s.cefr_level,
    s.cefr_decimal,
    s.cefr_numeric,
    s.justification,
    a.opportunity_id,
    p.first_name,
    p.last_name
   FROM (((appdata.audit_scores s
     JOIN appdata.audits a ON ((a.id = s.audit_id)))
     JOIN appdata.participants pt ON ((pt.id = a.participant_id)))
     LEFT JOIN appdata.people p ON ((p.id = pt.person_id)));


ALTER VIEW crm.v_audit_scores OWNER TO appdata_owner;

--
-- Name: v_offer_builder; Type: VIEW; Schema: crm; Owner: appdata_owner
--

CREATE VIEW crm.v_offer_builder AS
 SELECT off.id AS offer_id,
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
    c.id AS client_id,
    c.type AS client_type,
    p.first_name,
    p.last_name,
    org.name AS organization_name,
    rec.headline,
    rec.situation_description,
    rec.type AS recommendation_type,
    sc_overall.cefr_level AS cefr_overall,
    sc_range.cefr_level AS cefr_range,
    sc_accuracy.cefr_level AS cefr_accuracy,
    sc_fluency.cefr_level AS cefr_fluency,
    sc_comm.cefr_level AS cefr_communicativeness,
    item1.product AS item1_product,
    item1.label AS item1_label,
    item1.hours AS item1_hours,
    item1.format AS item1_format,
    item1.pricing_tier_id AS item1_pricing_tier_id,
    item1.unit_price_pln AS item1_price_pln,
    item2.product AS item2_product,
    item2.label AS item2_label,
    item2.hours AS item2_hours,
    item2.format AS item2_format,
    item2.pricing_tier_id AS item2_pricing_tier_id,
    item2.unit_price_pln AS item2_price_pln
   FROM ((((((((((((appdata.offers off
     JOIN appdata.opportunities o ON ((o.id = off.opportunity_id)))
     JOIN appdata.clients c ON ((c.id = o.client_id)))
     LEFT JOIN appdata.people p ON ((p.id = c.primary_contact_id)))
     LEFT JOIN appdata.organizations org ON ((org.id = c.organization_id)))
     LEFT JOIN appdata.recommendations rec ON ((rec.id = off.recommendation_id)))
     LEFT JOIN appdata.audit_scores sc_overall ON (((sc_overall.audit_id = rec.audit_id) AND (sc_overall.dimension = 'overall'::text))))
     LEFT JOIN appdata.audit_scores sc_range ON (((sc_range.audit_id = rec.audit_id) AND (sc_range.dimension = 'range'::text))))
     LEFT JOIN appdata.audit_scores sc_accuracy ON (((sc_accuracy.audit_id = rec.audit_id) AND (sc_accuracy.dimension = 'accuracy'::text))))
     LEFT JOIN appdata.audit_scores sc_fluency ON (((sc_fluency.audit_id = rec.audit_id) AND (sc_fluency.dimension = 'fluency'::text))))
     LEFT JOIN appdata.audit_scores sc_comm ON (((sc_comm.audit_id = rec.audit_id) AND (sc_comm.dimension = 'communicativeness'::text))))
     LEFT JOIN appdata.offer_items item1 ON (((item1.offer_id = off.id) AND (item1."position" = 1))))
     LEFT JOIN appdata.offer_items item2 ON (((item2.offer_id = off.id) AND (item2."position" = 2))));


ALTER VIEW crm.v_offer_builder OWNER TO appdata_owner;

--
-- Name: v_offer_goals; Type: VIEW; Schema: crm; Owner: appdata_owner
--

CREATE VIEW crm.v_offer_goals AS
 SELECT rg.id AS goal_id,
    rg.recommendation_id,
    rg."position",
    rg.title,
    rg.body,
    rg.stage_label,
    off.id AS offer_id
   FROM ((appdata.recommendation_goals rg
     JOIN appdata.recommendations rec ON ((rec.id = rg.recommendation_id)))
     LEFT JOIN appdata.offers off ON ((off.recommendation_id = rec.id)));


ALTER VIEW crm.v_offer_goals OWNER TO appdata_owner;

--
-- Name: v_opportunity_dates; Type: VIEW; Schema: crm; Owner: appdata_owner
--

CREATE VIEW crm.v_opportunity_dates AS
 SELECT opportunity_id,
    max(changed_at) FILTER (WHERE (to_stage = 'nowa'::appdata.opp_stage)) AS data_nowa,
    max(changed_at) FILTER (WHERE (to_stage = 'badanie_potrzeb'::appdata.opp_stage)) AS data_badanie_potrzeb,
    max(changed_at) FILTER (WHERE (to_stage = 'demo'::appdata.opp_stage)) AS data_demo,
    max(changed_at) FILTER (WHERE (to_stage = 'przygotowanie_oferty'::appdata.opp_stage)) AS data_przygotowanie_oferty,
    max(changed_at) FILTER (WHERE (to_stage = 'oferta_wyslana'::appdata.opp_stage)) AS data_oferta_wyslana,
    max(changed_at) FILTER (WHERE (to_stage = 'omowienie_oferty'::appdata.opp_stage)) AS data_omowienie_oferty,
    max(changed_at) FILTER (WHERE (to_stage = 'umowa_wyslana'::appdata.opp_stage)) AS data_umowa_wyslana,
    max(changed_at) FILTER (WHERE (to_stage = 'umowa_podpisana'::appdata.opp_stage)) AS data_umowa_podpisana,
    max(changed_at) FILTER (WHERE (to_stage = 'utracona'::appdata.opp_stage)) AS data_utracona,
    max(changed_at) FILTER (WHERE (to_stage = 'archiwum'::appdata.opp_stage)) AS data_archiwum
   FROM appdata.opportunity_stage_history
  GROUP BY opportunity_id;


ALTER VIEW crm.v_opportunity_dates OWNER TO appdata_owner;

--
-- Name: v_pipeline; Type: VIEW; Schema: crm; Owner: appdata_owner
--

CREATE VIEW crm.v_pipeline AS
 SELECT o.id AS opportunity_id,
    o.stage,
    o.state,
    o.value_pln,
    o.label,
    o.next_action_at,
    o.next_action,
    o.notes,
    o.loss_reason,
    c.id AS client_id,
    c.type AS client_type,
    c.qualification,
    p.first_name,
    p.last_name,
    p.email,
    org.name AS organization_name,
    u.full_name AS owner_name,
    o.created_at,
    o.updated_at
   FROM ((((appdata.opportunities o
     JOIN appdata.clients c ON ((c.id = o.client_id)))
     LEFT JOIN appdata.people p ON ((p.id = c.primary_contact_id)))
     LEFT JOIN appdata.organizations org ON ((org.id = c.organization_id)))
     LEFT JOIN appdata.users u ON ((u.id = c.owner_user_id)));


ALTER VIEW crm.v_pipeline OWNER TO appdata_owner;

--
-- Name: v_pricing; Type: VIEW; Schema: crm; Owner: appdata_owner
--

CREATE VIEW crm.v_pricing AS
 SELECT id AS pricing_tier_id,
    product,
    hours,
    format,
    price_pln,
    valid_from,
    valid_to
   FROM appdata.pricing_tiers
  WHERE ((valid_to IS NULL) OR (valid_to >= CURRENT_DATE));


ALTER VIEW crm.v_pricing OWNER TO appdata_owner;

--
-- Name: v_tasks; Type: VIEW; Schema: crm; Owner: appdata_owner
--

CREATE VIEW crm.v_tasks AS
 SELECT t.id AS task_id,
    t.entity_type,
    t.entity_id,
    t.title,
    t.stage_ref,
    t.status,
    t.due_at,
    t.payload,
    t.created_at,
    t.completed_at,
    u.id AS assignee_user_id,
    u.full_name AS assignee_name
   FROM (appdata.tasks t
     LEFT JOIN appdata.users u ON ((u.id = t.assignee_user_id)));


ALTER VIEW crm.v_tasks OWNER TO appdata_owner;

--
-- Name: v_testimonials; Type: VIEW; Schema: crm; Owner: appdata_owner
--

CREATE VIEW crm.v_testimonials AS
 SELECT id AS testimonial_id,
    author,
    role,
    quote,
    tags,
    slide_template_idx,
    active
   FROM appdata.testimonials;


ALTER VIEW crm.v_testimonials OWNER TO appdata_owner;

--
-- Name: audit_scores id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.audit_scores ALTER COLUMN id SET DEFAULT nextval('appdata.audit_scores_id_seq'::regclass);


--
-- Name: audits id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.audits ALTER COLUMN id SET DEFAULT nextval('appdata.audits_id_seq'::regclass);


--
-- Name: clients id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.clients ALTER COLUMN id SET DEFAULT nextval('appdata.clients_id_seq'::regclass);


--
-- Name: discovery_calls id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.discovery_calls ALTER COLUMN id SET DEFAULT nextval('appdata.discovery_calls_id_seq'::regclass);


--
-- Name: extractions id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.extractions ALTER COLUMN id SET DEFAULT nextval('appdata.extractions_id_seq'::regclass);


--
-- Name: files id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.files ALTER COLUMN id SET DEFAULT nextval('appdata.files_id_seq'::regclass);


--
-- Name: job_queue id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.job_queue ALTER COLUMN id SET DEFAULT nextval('appdata.job_queue_id_seq'::regclass);


--
-- Name: offer_items id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.offer_items ALTER COLUMN id SET DEFAULT nextval('appdata.offer_items_id_seq'::regclass);


--
-- Name: offer_snapshots id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.offer_snapshots ALTER COLUMN id SET DEFAULT nextval('appdata.offer_snapshots_id_seq'::regclass);


--
-- Name: offer_templates id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.offer_templates ALTER COLUMN id SET DEFAULT nextval('appdata.offer_templates_id_seq'::regclass);


--
-- Name: offers id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.offers ALTER COLUMN id SET DEFAULT nextval('appdata.offers_id_seq'::regclass);


--
-- Name: opportunities id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.opportunities ALTER COLUMN id SET DEFAULT nextval('appdata.opportunities_id_seq'::regclass);


--
-- Name: opportunity_stage_history id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.opportunity_stage_history ALTER COLUMN id SET DEFAULT nextval('appdata.opportunity_stage_history_id_seq'::regclass);


--
-- Name: organizations id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.organizations ALTER COLUMN id SET DEFAULT nextval('appdata.organizations_id_seq'::regclass);


--
-- Name: participants id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.participants ALTER COLUMN id SET DEFAULT nextval('appdata.participants_id_seq'::regclass);


--
-- Name: people id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.people ALTER COLUMN id SET DEFAULT nextval('appdata.people_id_seq'::regclass);


--
-- Name: pricing_tiers id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.pricing_tiers ALTER COLUMN id SET DEFAULT nextval('appdata.pricing_tiers_id_seq'::regclass);


--
-- Name: recommendation_goals id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.recommendation_goals ALTER COLUMN id SET DEFAULT nextval('appdata.recommendation_goals_id_seq'::regclass);


--
-- Name: recommendations id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.recommendations ALTER COLUMN id SET DEFAULT nextval('appdata.recommendations_id_seq'::regclass);


--
-- Name: tasks id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.tasks ALTER COLUMN id SET DEFAULT nextval('appdata.tasks_id_seq'::regclass);


--
-- Name: testimonials id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.testimonials ALTER COLUMN id SET DEFAULT nextval('appdata.testimonials_id_seq'::regclass);


--
-- Name: transcripts id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.transcripts ALTER COLUMN id SET DEFAULT nextval('appdata.transcripts_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.users ALTER COLUMN id SET DEFAULT nextval('appdata.users_id_seq'::regclass);


--
-- Name: audit_scores audit_scores_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.audit_scores
    ADD CONSTRAINT audit_scores_pkey PRIMARY KEY (id);


--
-- Name: audits audits_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.audits
    ADD CONSTRAINT audits_pkey PRIMARY KEY (id);


--
-- Name: clients clients_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.clients
    ADD CONSTRAINT clients_pkey PRIMARY KEY (id);


--
-- Name: discovery_calls discovery_calls_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.discovery_calls
    ADD CONSTRAINT discovery_calls_pkey PRIMARY KEY (id);


--
-- Name: extractions extractions_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.extractions
    ADD CONSTRAINT extractions_pkey PRIMARY KEY (id);


--
-- Name: files files_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.files
    ADD CONSTRAINT files_pkey PRIMARY KEY (id);


--
-- Name: job_queue job_queue_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.job_queue
    ADD CONSTRAINT job_queue_pkey PRIMARY KEY (id);


--
-- Name: offer_items offer_items_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.offer_items
    ADD CONSTRAINT offer_items_pkey PRIMARY KEY (id);


--
-- Name: offer_snapshots offer_snapshots_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.offer_snapshots
    ADD CONSTRAINT offer_snapshots_pkey PRIMARY KEY (id);


--
-- Name: offer_templates offer_templates_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.offer_templates
    ADD CONSTRAINT offer_templates_pkey PRIMARY KEY (id);


--
-- Name: offers offers_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.offers
    ADD CONSTRAINT offers_pkey PRIMARY KEY (id);


--
-- Name: opportunities opportunities_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.opportunities
    ADD CONSTRAINT opportunities_pkey PRIMARY KEY (id);


--
-- Name: opportunity_stage_history opportunity_stage_history_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.opportunity_stage_history
    ADD CONSTRAINT opportunity_stage_history_pkey PRIMARY KEY (id);


--
-- Name: organizations organizations_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (id);


--
-- Name: participants participants_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.participants
    ADD CONSTRAINT participants_pkey PRIMARY KEY (id);


--
-- Name: people people_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.people
    ADD CONSTRAINT people_pkey PRIMARY KEY (id);


--
-- Name: pricing_tiers pricing_tiers_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.pricing_tiers
    ADD CONSTRAINT pricing_tiers_pkey PRIMARY KEY (id);


--
-- Name: recommendation_goals recommendation_goals_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.recommendation_goals
    ADD CONSTRAINT recommendation_goals_pkey PRIMARY KEY (id);


--
-- Name: recommendations recommendations_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.recommendations
    ADD CONSTRAINT recommendations_pkey PRIMARY KEY (id);


--
-- Name: tasks tasks_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.tasks
    ADD CONSTRAINT tasks_pkey PRIMARY KEY (id);


--
-- Name: testimonials testimonials_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.testimonials
    ADD CONSTRAINT testimonials_pkey PRIMARY KEY (id);


--
-- Name: transcripts transcripts_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.transcripts
    ADD CONSTRAINT transcripts_pkey PRIMARY KEY (id);


--
-- Name: audit_scores uq_audit_scores_audit_dimension; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.audit_scores
    ADD CONSTRAINT uq_audit_scores_audit_dimension UNIQUE (audit_id, dimension);


--
-- Name: offer_items uq_offer_items_position; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.offer_items
    ADD CONSTRAINT uq_offer_items_position UNIQUE (offer_id, "position");


--
-- Name: offers uq_offers_opportunity_version; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.offers
    ADD CONSTRAINT uq_offers_opportunity_version UNIQUE (opportunity_id, version);


--
-- Name: pricing_tiers uq_pricing_tiers_natural_key; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.pricing_tiers
    ADD CONSTRAINT uq_pricing_tiers_natural_key UNIQUE (product, hours, format, valid_from);


--
-- Name: recommendation_goals uq_recommendation_goals_position; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.recommendation_goals
    ADD CONSTRAINT uq_recommendation_goals_position UNIQUE (recommendation_id, "position");


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: idx_audits_opportunity_id; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_audits_opportunity_id ON appdata.audits USING btree (opportunity_id);


--
-- Name: idx_audits_participant_id; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_audits_participant_id ON appdata.audits USING btree (participant_id);


--
-- Name: idx_clients_organization_id; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_clients_organization_id ON appdata.clients USING btree (organization_id);


--
-- Name: idx_clients_owner_user_id; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_clients_owner_user_id ON appdata.clients USING btree (owner_user_id);


--
-- Name: idx_clients_primary_contact_id; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_clients_primary_contact_id ON appdata.clients USING btree (primary_contact_id);


--
-- Name: idx_discovery_calls_opportunity_id; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_discovery_calls_opportunity_id ON appdata.discovery_calls USING btree (opportunity_id);


--
-- Name: idx_extractions_transcript_id; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_extractions_transcript_id ON appdata.extractions USING btree (transcript_id);


--
-- Name: idx_files_bucket_key; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE UNIQUE INDEX idx_files_bucket_key ON appdata.files USING btree (bucket, key);


--
-- Name: idx_job_queue_dispatch; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_job_queue_dispatch ON appdata.job_queue USING btree (status, priority DESC, created_at) WHERE (status = 'queued'::appdata.job_status);


--
-- Name: idx_offer_items_offer_id; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_offer_items_offer_id ON appdata.offer_items USING btree (offer_id);


--
-- Name: idx_offer_snapshots_offer_id; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_offer_snapshots_offer_id ON appdata.offer_snapshots USING btree (offer_id);


--
-- Name: idx_offers_opportunity_id; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_offers_opportunity_id ON appdata.offers USING btree (opportunity_id);


--
-- Name: idx_offers_recommendation_id; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_offers_recommendation_id ON appdata.offers USING btree (recommendation_id);


--
-- Name: idx_opportunities_client_id; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_opportunities_client_id ON appdata.opportunities USING btree (client_id);


--
-- Name: idx_opportunities_stage; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_opportunities_stage ON appdata.opportunities USING btree (stage);


--
-- Name: idx_opportunity_stage_history_opportunity_id; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_opportunity_stage_history_opportunity_id ON appdata.opportunity_stage_history USING btree (opportunity_id, changed_at);


--
-- Name: idx_participants_client_id; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_participants_client_id ON appdata.participants USING btree (client_id);


--
-- Name: idx_people_email_unique; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE UNIQUE INDEX idx_people_email_unique ON appdata.people USING btree (email) WHERE (email IS NOT NULL);


--
-- Name: idx_people_organization_id; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_people_organization_id ON appdata.people USING btree (organization_id);


--
-- Name: idx_recommendations_audit_id; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_recommendations_audit_id ON appdata.recommendations USING btree (audit_id);


--
-- Name: idx_recommendations_opportunity_id; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_recommendations_opportunity_id ON appdata.recommendations USING btree (opportunity_id);


--
-- Name: idx_tasks_assignee_status; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_tasks_assignee_status ON appdata.tasks USING btree (assignee_user_id, status);


--
-- Name: idx_tasks_entity; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_tasks_entity ON appdata.tasks USING btree (entity_type, entity_id);


--
-- Name: idx_transcripts_curated_trgm; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_transcripts_curated_trgm ON appdata.transcripts USING gin (curated_text appdata.gin_trgm_ops);


--
-- Name: idx_transcripts_search_tsv; Type: INDEX; Schema: appdata; Owner: appdata_owner
--

CREATE INDEX idx_transcripts_search_tsv ON appdata.transcripts USING gin (search_tsv);


--
-- Name: offer_items trg_offer_items_recalc_totals; Type: TRIGGER; Schema: appdata; Owner: appdata_owner
--

CREATE TRIGGER trg_offer_items_recalc_totals AFTER INSERT OR DELETE OR UPDATE ON appdata.offer_items FOR EACH ROW EXECUTE FUNCTION appdata.trg_offer_items_recalc_totals_fn();


--
-- Name: offer_items trg_offer_items_set_unit_price; Type: TRIGGER; Schema: appdata; Owner: appdata_owner
--

CREATE TRIGGER trg_offer_items_set_unit_price BEFORE INSERT OR UPDATE ON appdata.offer_items FOR EACH ROW EXECUTE FUNCTION appdata.set_offer_item_unit_price();


--
-- Name: offers trg_offers_recalc_on_discount; Type: TRIGGER; Schema: appdata; Owner: appdata_owner
--

CREATE TRIGGER trg_offers_recalc_on_discount AFTER UPDATE OF discount_pct ON appdata.offers FOR EACH ROW WHEN ((old.discount_pct IS DISTINCT FROM new.discount_pct)) EXECUTE FUNCTION appdata.trg_offers_recalc_on_discount_fn();


--
-- Name: opportunities trg_opportunities_stage_history; Type: TRIGGER; Schema: appdata; Owner: appdata_owner
--

CREATE TRIGGER trg_opportunities_stage_history AFTER UPDATE OF stage ON appdata.opportunities FOR EACH ROW WHEN ((old.stage IS DISTINCT FROM new.stage)) EXECUTE FUNCTION appdata.log_opportunity_stage_change();


--
-- Name: opportunities trg_opportunities_updated_at; Type: TRIGGER; Schema: appdata; Owner: appdata_owner
--

CREATE TRIGGER trg_opportunities_updated_at BEFORE UPDATE ON appdata.opportunities FOR EACH ROW EXECUTE FUNCTION appdata.set_updated_at();


--
-- Name: users trg_users_updated_at; Type: TRIGGER; Schema: appdata; Owner: appdata_owner
--

CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON appdata.users FOR EACH ROW EXECUTE FUNCTION appdata.set_updated_at();


--
-- Name: v_audit_scores trg_v_audit_scores_instead_of_update; Type: TRIGGER; Schema: crm; Owner: appdata_owner
--

CREATE TRIGGER trg_v_audit_scores_instead_of_update INSTEAD OF UPDATE ON crm.v_audit_scores FOR EACH ROW EXECUTE FUNCTION crm.v_audit_scores_instead_of_update();


--
-- Name: v_offer_builder trg_v_offer_builder_instead_of_update; Type: TRIGGER; Schema: crm; Owner: appdata_owner
--

CREATE TRIGGER trg_v_offer_builder_instead_of_update INSTEAD OF UPDATE ON crm.v_offer_builder FOR EACH ROW EXECUTE FUNCTION crm.v_offer_builder_instead_of_update();


--
-- Name: v_offer_goals trg_v_offer_goals_instead_of; Type: TRIGGER; Schema: crm; Owner: appdata_owner
--

CREATE TRIGGER trg_v_offer_goals_instead_of INSTEAD OF INSERT OR DELETE OR UPDATE ON crm.v_offer_goals FOR EACH ROW EXECUTE FUNCTION crm.v_offer_goals_instead_of();


--
-- Name: v_pipeline trg_v_pipeline_instead_of_update; Type: TRIGGER; Schema: crm; Owner: appdata_owner
--

CREATE TRIGGER trg_v_pipeline_instead_of_update INSTEAD OF UPDATE ON crm.v_pipeline FOR EACH ROW EXECUTE FUNCTION crm.v_pipeline_instead_of_update();


--
-- Name: v_tasks trg_v_tasks_instead_of_update; Type: TRIGGER; Schema: crm; Owner: appdata_owner
--

CREATE TRIGGER trg_v_tasks_instead_of_update INSTEAD OF UPDATE ON crm.v_tasks FOR EACH ROW EXECUTE FUNCTION crm.v_tasks_instead_of_update();


--
-- Name: audit_scores audit_scores_audit_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.audit_scores
    ADD CONSTRAINT audit_scores_audit_id_fkey FOREIGN KEY (audit_id) REFERENCES appdata.audits(id);


--
-- Name: audits audits_auditor_user_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.audits
    ADD CONSTRAINT audits_auditor_user_id_fkey FOREIGN KEY (auditor_user_id) REFERENCES appdata.users(id);


--
-- Name: audits audits_opportunity_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.audits
    ADD CONSTRAINT audits_opportunity_id_fkey FOREIGN KEY (opportunity_id) REFERENCES appdata.opportunities(id);


--
-- Name: audits audits_participant_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.audits
    ADD CONSTRAINT audits_participant_id_fkey FOREIGN KEY (participant_id) REFERENCES appdata.participants(id);


--
-- Name: clients clients_organization_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.clients
    ADD CONSTRAINT clients_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES appdata.organizations(id);


--
-- Name: clients clients_owner_user_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.clients
    ADD CONSTRAINT clients_owner_user_id_fkey FOREIGN KEY (owner_user_id) REFERENCES appdata.users(id);


--
-- Name: clients clients_primary_contact_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.clients
    ADD CONSTRAINT clients_primary_contact_id_fkey FOREIGN KEY (primary_contact_id) REFERENCES appdata.people(id);


--
-- Name: discovery_calls discovery_calls_opportunity_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.discovery_calls
    ADD CONSTRAINT discovery_calls_opportunity_id_fkey FOREIGN KEY (opportunity_id) REFERENCES appdata.opportunities(id);


--
-- Name: extractions extractions_accepted_by_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.extractions
    ADD CONSTRAINT extractions_accepted_by_fkey FOREIGN KEY (accepted_by) REFERENCES appdata.users(id);


--
-- Name: extractions extractions_transcript_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.extractions
    ADD CONSTRAINT extractions_transcript_id_fkey FOREIGN KEY (transcript_id) REFERENCES appdata.transcripts(id);


--
-- Name: files files_uploaded_by_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.files
    ADD CONSTRAINT files_uploaded_by_fkey FOREIGN KEY (uploaded_by) REFERENCES appdata.users(id);


--
-- Name: offer_items offer_items_offer_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.offer_items
    ADD CONSTRAINT offer_items_offer_id_fkey FOREIGN KEY (offer_id) REFERENCES appdata.offers(id);


--
-- Name: offer_items offer_items_pricing_tier_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.offer_items
    ADD CONSTRAINT offer_items_pricing_tier_id_fkey FOREIGN KEY (pricing_tier_id) REFERENCES appdata.pricing_tiers(id);


--
-- Name: offer_snapshots offer_snapshots_offer_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.offer_snapshots
    ADD CONSTRAINT offer_snapshots_offer_id_fkey FOREIGN KEY (offer_id) REFERENCES appdata.offers(id);


--
-- Name: offer_snapshots offer_snapshots_template_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.offer_snapshots
    ADD CONSTRAINT offer_snapshots_template_id_fkey FOREIGN KEY (template_id) REFERENCES appdata.offer_templates(id);


--
-- Name: offer_templates offer_templates_uploaded_by_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.offer_templates
    ADD CONSTRAINT offer_templates_uploaded_by_fkey FOREIGN KEY (uploaded_by) REFERENCES appdata.users(id);


--
-- Name: offers offers_created_by_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.offers
    ADD CONSTRAINT offers_created_by_fkey FOREIGN KEY (created_by) REFERENCES appdata.users(id);


--
-- Name: offers offers_opportunity_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.offers
    ADD CONSTRAINT offers_opportunity_id_fkey FOREIGN KEY (opportunity_id) REFERENCES appdata.opportunities(id);


--
-- Name: offers offers_recommendation_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.offers
    ADD CONSTRAINT offers_recommendation_id_fkey FOREIGN KEY (recommendation_id) REFERENCES appdata.recommendations(id);


--
-- Name: offers offers_template_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.offers
    ADD CONSTRAINT offers_template_id_fkey FOREIGN KEY (template_id) REFERENCES appdata.offer_templates(id);


--
-- Name: opportunities opportunities_client_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.opportunities
    ADD CONSTRAINT opportunities_client_id_fkey FOREIGN KEY (client_id) REFERENCES appdata.clients(id);


--
-- Name: opportunity_stage_history opportunity_stage_history_changed_by_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.opportunity_stage_history
    ADD CONSTRAINT opportunity_stage_history_changed_by_fkey FOREIGN KEY (changed_by) REFERENCES appdata.users(id);


--
-- Name: opportunity_stage_history opportunity_stage_history_opportunity_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.opportunity_stage_history
    ADD CONSTRAINT opportunity_stage_history_opportunity_id_fkey FOREIGN KEY (opportunity_id) REFERENCES appdata.opportunities(id);


--
-- Name: participants participants_client_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.participants
    ADD CONSTRAINT participants_client_id_fkey FOREIGN KEY (client_id) REFERENCES appdata.clients(id);


--
-- Name: participants participants_person_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.participants
    ADD CONSTRAINT participants_person_id_fkey FOREIGN KEY (person_id) REFERENCES appdata.people(id);


--
-- Name: people people_organization_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.people
    ADD CONSTRAINT people_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES appdata.organizations(id);


--
-- Name: recommendation_goals recommendation_goals_recommendation_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.recommendation_goals
    ADD CONSTRAINT recommendation_goals_recommendation_id_fkey FOREIGN KEY (recommendation_id) REFERENCES appdata.recommendations(id);


--
-- Name: recommendations recommendations_approved_by_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.recommendations
    ADD CONSTRAINT recommendations_approved_by_fkey FOREIGN KEY (approved_by) REFERENCES appdata.users(id);


--
-- Name: recommendations recommendations_audit_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.recommendations
    ADD CONSTRAINT recommendations_audit_id_fkey FOREIGN KEY (audit_id) REFERENCES appdata.audits(id);


--
-- Name: recommendations recommendations_opportunity_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.recommendations
    ADD CONSTRAINT recommendations_opportunity_id_fkey FOREIGN KEY (opportunity_id) REFERENCES appdata.opportunities(id);


--
-- Name: tasks tasks_assignee_user_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.tasks
    ADD CONSTRAINT tasks_assignee_user_id_fkey FOREIGN KEY (assignee_user_id) REFERENCES appdata.users(id);


--
-- Name: transcripts transcripts_audit_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.transcripts
    ADD CONSTRAINT transcripts_audit_id_fkey FOREIGN KEY (audit_id) REFERENCES appdata.audits(id);


--
-- Name: transcripts transcripts_discovery_call_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.transcripts
    ADD CONSTRAINT transcripts_discovery_call_id_fkey FOREIGN KEY (discovery_call_id) REFERENCES appdata.discovery_calls(id);


--
-- Name: transcripts transcripts_recording_file_id_fkey; Type: FK CONSTRAINT; Schema: appdata; Owner: appdata_owner
--

ALTER TABLE ONLY appdata.transcripts
    ADD CONSTRAINT transcripts_recording_file_id_fkey FOREIGN KEY (recording_file_id) REFERENCES appdata.files(id);


--
-- Name: SCHEMA crm; Type: ACL; Schema: -; Owner: appdata_owner
--

GRANT USAGE ON SCHEMA crm TO nocodb_crm_user;
GRANT USAGE ON SCHEMA crm TO n8n_crm_user;


--
-- Name: TABLE v_audit_scores; Type: ACL; Schema: crm; Owner: appdata_owner
--

GRANT SELECT,UPDATE ON TABLE crm.v_audit_scores TO nocodb_crm_user;


--
-- Name: TABLE v_offer_builder; Type: ACL; Schema: crm; Owner: appdata_owner
--

GRANT SELECT,UPDATE ON TABLE crm.v_offer_builder TO nocodb_crm_user;
GRANT SELECT,UPDATE ON TABLE crm.v_offer_builder TO n8n_crm_user;


--
-- Name: TABLE v_offer_goals; Type: ACL; Schema: crm; Owner: appdata_owner
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE crm.v_offer_goals TO nocodb_crm_user;


--
-- Name: TABLE v_opportunity_dates; Type: ACL; Schema: crm; Owner: appdata_owner
--

GRANT SELECT ON TABLE crm.v_opportunity_dates TO nocodb_crm_user;


--
-- Name: TABLE v_pipeline; Type: ACL; Schema: crm; Owner: appdata_owner
--

GRANT SELECT,UPDATE ON TABLE crm.v_pipeline TO nocodb_crm_user;


--
-- Name: TABLE v_pricing; Type: ACL; Schema: crm; Owner: appdata_owner
--

GRANT SELECT ON TABLE crm.v_pricing TO nocodb_crm_user;


--
-- Name: TABLE v_tasks; Type: ACL; Schema: crm; Owner: appdata_owner
--

GRANT SELECT,UPDATE ON TABLE crm.v_tasks TO nocodb_crm_user;


--
-- Name: TABLE v_testimonials; Type: ACL; Schema: crm; Owner: appdata_owner
--

GRANT SELECT ON TABLE crm.v_testimonials TO nocodb_crm_user;


--
-- PostgreSQL database dump complete
--

\unrestrict TZchxPdxenEy9ZVRCkzxPEIfegdmtu7ROclHQncrwmKlhZePWdycVIvDQ3Eo8Uq

