--
-- PostgreSQL database dump
--

\restrict 5qesuY6nM5uDuhQY5OvWU8SZXxeApZhDJL75OphymP2IEjgdVZyjEbkbgObTPdl

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
-- Name: crm; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA crm;


ALTER SCHEMA crm OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: Activities; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."Activities" (
    id integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    created_by character varying,
    updated_by character varying,
    nc_order numeric,
    nc_row_meta jsonb,
    summary text,
    type text,
    triggered_by text,
    flow text,
    payload text
);


ALTER TABLE crm."Activities" OWNER TO nocodb_crm_user;

--
-- Name: Activities_id_seq; Type: SEQUENCE; Schema: crm; Owner: nocodb_crm_user
--

CREATE SEQUENCE crm."Activities_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE crm."Activities_id_seq" OWNER TO nocodb_crm_user;

--
-- Name: Activities_id_seq; Type: SEQUENCE OWNED BY; Schema: crm; Owner: nocodb_crm_user
--

ALTER SEQUENCE crm."Activities_id_seq" OWNED BY crm."Activities".id;


--
-- Name: Assesments; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."Assesments" (
    id integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    created_by character varying,
    updated_by character varying,
    nc_order numeric,
    nc_row_meta jsonb,
    title text,
    "Level" text,
    cefr_overall text,
    cefr_range text,
    cefr_accuracy text,
    cefr_fluency text,
    cefr_communication text
);


ALTER TABLE crm."Assesments" OWNER TO nocodb_crm_user;

--
-- Name: Assesments_id_seq; Type: SEQUENCE; Schema: crm; Owner: nocodb_crm_user
--

CREATE SEQUENCE crm."Assesments_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE crm."Assesments_id_seq" OWNER TO nocodb_crm_user;

--
-- Name: Assesments_id_seq; Type: SEQUENCE OWNED BY; Schema: crm; Owner: nocodb_crm_user
--

ALTER SEQUENCE crm."Assesments_id_seq" OWNED BY crm."Assesments".id;


--
-- Name: Companies; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."Companies" (
    id integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    created_by character varying,
    updated_by character varying,
    nc_order numeric,
    nc_row_meta jsonb,
    name text,
    domains text,
    nip text,
    industry text,
    size text,
    folder_url text,
    notes text
);


ALTER TABLE crm."Companies" OWNER TO nocodb_crm_user;

--
-- Name: Companies_id_seq; Type: SEQUENCE; Schema: crm; Owner: nocodb_crm_user
--

CREATE SEQUENCE crm."Companies_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE crm."Companies_id_seq" OWNER TO nocodb_crm_user;

--
-- Name: Companies_id_seq; Type: SEQUENCE OWNED BY; Schema: crm; Owner: nocodb_crm_user
--

ALTER SEQUENCE crm."Companies_id_seq" OWNED BY crm."Companies".id;


--
-- Name: Leads; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."Leads" (
    id integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    created_by character varying,
    updated_by character varying,
    nc_order numeric,
    nc_row_meta jsonb,
    name text,
    contact_name text,
    contact_email character varying,
    contact_phone character varying,
    type text DEFAULT 'B2C'::text,
    owner character varying,
    source text,
    qualification text,
    disqualify_reason text,
    disqualify_note text,
    stage text,
    value numeric,
    state text,
    label text,
    company_match_status text,
    offer_prep_status text,
    training_goals text,
    offer_sent_at date,
    contract_sent_at date,
    closed_at date,
    note text,
    duplicate_check text,
    lead_id bigint,
    contact_note text
);


ALTER TABLE crm."Leads" OWNER TO nocodb_crm_user;

--
-- Name: Leads_id_seq; Type: SEQUENCE; Schema: crm; Owner: nocodb_crm_user
--

CREATE SEQUENCE crm."Leads_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE crm."Leads_id_seq" OWNER TO nocodb_crm_user;

--
-- Name: Leads_id_seq; Type: SEQUENCE OWNED BY; Schema: crm; Owner: nocodb_crm_user
--

ALTER SEQUENCE crm."Leads_id_seq" OWNED BY crm."Leads".id;


--
-- Name: Meetings; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."Meetings" (
    id integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    created_by character varying,
    updated_by character varying,
    nc_order numeric,
    nc_row_meta jsonb,
    title text,
    type text,
    starts_at timestamp without time zone,
    ends_at timestamp without time zone,
    owner character varying,
    transcript text,
    ai_analysis text,
    notes text,
    processing_status text,
    outcome text,
    status text
);


ALTER TABLE crm."Meetings" OWNER TO nocodb_crm_user;

--
-- Name: Meetings_id_seq; Type: SEQUENCE; Schema: crm; Owner: nocodb_crm_user
--

CREATE SEQUENCE crm."Meetings_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE crm."Meetings_id_seq" OWNER TO nocodb_crm_user;

--
-- Name: Meetings_id_seq; Type: SEQUENCE OWNED BY; Schema: crm; Owner: nocodb_crm_user
--

ALTER SEQUENCE crm."Meetings_id_seq" OWNED BY crm."Meetings".id;


--
-- Name: Offer_templates; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."Offer_templates" (
    id integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    created_by character varying,
    updated_by character varying,
    nc_order numeric,
    nc_row_meta jsonb,
    name text,
    file text,
    active boolean DEFAULT false,
    notes text
);


ALTER TABLE crm."Offer_templates" OWNER TO nocodb_crm_user;

--
-- Name: Offer_templates_id_seq; Type: SEQUENCE; Schema: crm; Owner: nocodb_crm_user
--

CREATE SEQUENCE crm."Offer_templates_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE crm."Offer_templates_id_seq" OWNER TO nocodb_crm_user;

--
-- Name: Offer_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: crm; Owner: nocodb_crm_user
--

ALTER SEQUENCE crm."Offer_templates_id_seq" OWNED BY crm."Offer_templates".id;


--
-- Name: Offers; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."Offers" (
    id integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    created_by character varying,
    updated_by character varying,
    nc_order numeric,
    nc_row_meta jsonb,
    title text,
    status text,
    price numeric,
    template_name text,
    file text,
    "Text" text,
    data_json text,
    warnings text
);


ALTER TABLE crm."Offers" OWNER TO nocodb_crm_user;

--
-- Name: Offers_id_seq; Type: SEQUENCE; Schema: crm; Owner: nocodb_crm_user
--

CREATE SEQUENCE crm."Offers_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE crm."Offers_id_seq" OWNER TO nocodb_crm_user;

--
-- Name: Offers_id_seq; Type: SEQUENCE OWNED BY; Schema: crm; Owner: nocodb_crm_user
--

ALTER SEQUENCE crm."Offers_id_seq" OWNED BY crm."Offers".id;


--
-- Name: Participants; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."Participants" (
    id integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    created_by character varying,
    updated_by character varying,
    nc_order numeric,
    nc_row_meta jsonb,
    full_name text,
    "position" text,
    linkedin_url text,
    email character varying,
    cefr_overall text,
    cefr_range text,
    cefr_accuracy text,
    cefr_fluency text,
    cefr_communication text,
    audit_notes text,
    needs_summary text,
    assigned_methodologist character varying
);


ALTER TABLE crm."Participants" OWNER TO nocodb_crm_user;

--
-- Name: Participants_id_seq; Type: SEQUENCE; Schema: crm; Owner: nocodb_crm_user
--

CREATE SEQUENCE crm."Participants_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE crm."Participants_id_seq" OWNER TO nocodb_crm_user;

--
-- Name: Participants_id_seq; Type: SEQUENCE OWNED BY; Schema: crm; Owner: nocodb_crm_user
--

ALTER SEQUENCE crm."Participants_id_seq" OWNED BY crm."Participants".id;


--
-- Name: Projects; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."Projects" (
    id integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    created_by character varying,
    updated_by character varying,
    nc_order numeric,
    nc_row_meta jsonb,
    name text,
    team text,
    active boolean DEFAULT false
);


ALTER TABLE crm."Projects" OWNER TO nocodb_crm_user;

--
-- Name: Projects_id_seq; Type: SEQUENCE; Schema: crm; Owner: nocodb_crm_user
--

CREATE SEQUENCE crm."Projects_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE crm."Projects_id_seq" OWNER TO nocodb_crm_user;

--
-- Name: Projects_id_seq; Type: SEQUENCE OWNED BY; Schema: crm; Owner: nocodb_crm_user
--

ALTER SEQUENCE crm."Projects_id_seq" OWNED BY crm."Projects".id;


--
-- Name: Task_templates; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."Task_templates" (
    id integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    created_by character varying,
    updated_by character varying,
    nc_order numeric,
    nc_row_meta jsonb,
    title text,
    active boolean DEFAULT false
);


ALTER TABLE crm."Task_templates" OWNER TO nocodb_crm_user;

--
-- Name: Task_templates_id_seq; Type: SEQUENCE; Schema: crm; Owner: nocodb_crm_user
--

CREATE SEQUENCE crm."Task_templates_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE crm."Task_templates_id_seq" OWNER TO nocodb_crm_user;

--
-- Name: Task_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: crm; Owner: nocodb_crm_user
--

ALTER SEQUENCE crm."Task_templates_id_seq" OWNED BY crm."Task_templates".id;


--
-- Name: Tasks; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."Tasks" (
    id integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    created_by character varying,
    updated_by character varying,
    nc_order numeric,
    nc_row_meta jsonb,
    title text,
    assignee character varying,
    due_date date,
    status text,
    priority text,
    description text,
    created_by_flow text
);


ALTER TABLE crm."Tasks" OWNER TO nocodb_crm_user;

--
-- Name: Tasks_id_seq; Type: SEQUENCE; Schema: crm; Owner: nocodb_crm_user
--

CREATE SEQUENCE crm."Tasks_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE crm."Tasks_id_seq" OWNER TO nocodb_crm_user;

--
-- Name: Tasks_id_seq; Type: SEQUENCE OWNED BY; Schema: crm; Owner: nocodb_crm_user
--

ALTER SEQUENCE crm."Tasks_id_seq" OWNED BY crm."Tasks".id;


--
-- Name: Testimonials; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."Testimonials" (
    id integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    created_by character varying,
    updated_by character varying,
    nc_order numeric,
    nc_row_meta jsonb,
    title text,
    client_name text,
    content text
);


ALTER TABLE crm."Testimonials" OWNER TO nocodb_crm_user;

--
-- Name: Testimonials_id_seq; Type: SEQUENCE; Schema: crm; Owner: nocodb_crm_user
--

CREATE SEQUENCE crm."Testimonials_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE crm."Testimonials_id_seq" OWNER TO nocodb_crm_user;

--
-- Name: Testimonials_id_seq; Type: SEQUENCE OWNED BY; Schema: crm; Owner: nocodb_crm_user
--

ALTER SEQUENCE crm."Testimonials_id_seq" OWNED BY crm."Testimonials".id;


--
-- Name: _nc_m2m_Activities_Leads; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."_nc_m2m_Activities_Leads" (
    "Leads_id" integer NOT NULL,
    "Activities_id" integer NOT NULL
);


ALTER TABLE crm."_nc_m2m_Activities_Leads" OWNER TO nocodb_crm_user;

--
-- Name: _nc_m2m_Activities_Meetings; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."_nc_m2m_Activities_Meetings" (
    "Meetings_id" integer NOT NULL,
    "Activities_id" integer NOT NULL
);


ALTER TABLE crm."_nc_m2m_Activities_Meetings" OWNER TO nocodb_crm_user;

--
-- Name: _nc_m2m_Activities_Tasks; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."_nc_m2m_Activities_Tasks" (
    "Tasks_id" integer NOT NULL,
    "Activities_id" integer NOT NULL
);


ALTER TABLE crm."_nc_m2m_Activities_Tasks" OWNER TO nocodb_crm_user;

--
-- Name: _nc_m2m_Assesments_Participants; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."_nc_m2m_Assesments_Participants" (
    "Participants_id" integer NOT NULL,
    "Assesments_id" integer NOT NULL
);


ALTER TABLE crm."_nc_m2m_Assesments_Participants" OWNER TO nocodb_crm_user;

--
-- Name: _nc_m2m_Companies_Leads; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."_nc_m2m_Companies_Leads" (
    "Leads_id" integer NOT NULL,
    "Companies_id" integer NOT NULL
);


ALTER TABLE crm."_nc_m2m_Companies_Leads" OWNER TO nocodb_crm_user;

--
-- Name: _nc_m2m_Companies_Participants; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."_nc_m2m_Companies_Participants" (
    "Participants_id" integer NOT NULL,
    "Companies_id" integer NOT NULL
);


ALTER TABLE crm."_nc_m2m_Companies_Participants" OWNER TO nocodb_crm_user;

--
-- Name: _nc_m2m_Leads_Leads; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."_nc_m2m_Leads_Leads" (
    "Leads1_id" integer NOT NULL,
    "Leads_id" integer NOT NULL
);


ALTER TABLE crm."_nc_m2m_Leads_Leads" OWNER TO nocodb_crm_user;

--
-- Name: _nc_m2m_Leads_Meetings; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."_nc_m2m_Leads_Meetings" (
    "Meetings_id" integer NOT NULL,
    "Leads_id" integer NOT NULL
);


ALTER TABLE crm."_nc_m2m_Leads_Meetings" OWNER TO nocodb_crm_user;

--
-- Name: _nc_m2m_Leads_Participants; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."_nc_m2m_Leads_Participants" (
    "Participants_id" integer NOT NULL,
    "Leads_id" integer NOT NULL
);


ALTER TABLE crm."_nc_m2m_Leads_Participants" OWNER TO nocodb_crm_user;

--
-- Name: _nc_m2m_Leads_Tasks; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."_nc_m2m_Leads_Tasks" (
    "Tasks_id" integer NOT NULL,
    "Leads_id" integer NOT NULL
);


ALTER TABLE crm."_nc_m2m_Leads_Tasks" OWNER TO nocodb_crm_user;

--
-- Name: _nc_m2m_Leads_Testimonials; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."_nc_m2m_Leads_Testimonials" (
    "Testimonials_id" integer NOT NULL,
    "Leads_id" integer NOT NULL
);


ALTER TABLE crm."_nc_m2m_Leads_Testimonials" OWNER TO nocodb_crm_user;

--
-- Name: _nc_m2m_Offers_Leads; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."_nc_m2m_Offers_Leads" (
    "Leads_id" integer NOT NULL,
    "Offers_id" integer NOT NULL
);


ALTER TABLE crm."_nc_m2m_Offers_Leads" OWNER TO nocodb_crm_user;

--
-- Name: _nc_m2m_Participants_Meetings; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."_nc_m2m_Participants_Meetings" (
    "Meetings_id" integer NOT NULL,
    "Participants_id" integer NOT NULL
);


ALTER TABLE crm."_nc_m2m_Participants_Meetings" OWNER TO nocodb_crm_user;

--
-- Name: _nc_m2m_Task_templates_Projects; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."_nc_m2m_Task_templates_Projects" (
    "Projects_id" integer NOT NULL,
    "Task_templates_id" integer NOT NULL
);


ALTER TABLE crm."_nc_m2m_Task_templates_Projects" OWNER TO nocodb_crm_user;

--
-- Name: _nc_m2m_Tasks_Projects; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."_nc_m2m_Tasks_Projects" (
    "Projects_id" integer NOT NULL,
    "Tasks_id" integer NOT NULL
);


ALTER TABLE crm."_nc_m2m_Tasks_Projects" OWNER TO nocodb_crm_user;

--
-- Name: _nc_m2m_Tasks_Task_templates; Type: TABLE; Schema: crm; Owner: nocodb_crm_user
--

CREATE TABLE crm."_nc_m2m_Tasks_Task_templates" (
    "Task_templates_id" integer NOT NULL,
    "Tasks_id" integer NOT NULL
);


ALTER TABLE crm."_nc_m2m_Tasks_Task_templates" OWNER TO nocodb_crm_user;

--
-- Name: Activities id; Type: DEFAULT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Activities" ALTER COLUMN id SET DEFAULT nextval('crm."Activities_id_seq"'::regclass);


--
-- Name: Assesments id; Type: DEFAULT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Assesments" ALTER COLUMN id SET DEFAULT nextval('crm."Assesments_id_seq"'::regclass);


--
-- Name: Companies id; Type: DEFAULT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Companies" ALTER COLUMN id SET DEFAULT nextval('crm."Companies_id_seq"'::regclass);


--
-- Name: Leads id; Type: DEFAULT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Leads" ALTER COLUMN id SET DEFAULT nextval('crm."Leads_id_seq"'::regclass);


--
-- Name: Meetings id; Type: DEFAULT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Meetings" ALTER COLUMN id SET DEFAULT nextval('crm."Meetings_id_seq"'::regclass);


--
-- Name: Offer_templates id; Type: DEFAULT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Offer_templates" ALTER COLUMN id SET DEFAULT nextval('crm."Offer_templates_id_seq"'::regclass);


--
-- Name: Offers id; Type: DEFAULT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Offers" ALTER COLUMN id SET DEFAULT nextval('crm."Offers_id_seq"'::regclass);


--
-- Name: Participants id; Type: DEFAULT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Participants" ALTER COLUMN id SET DEFAULT nextval('crm."Participants_id_seq"'::regclass);


--
-- Name: Projects id; Type: DEFAULT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Projects" ALTER COLUMN id SET DEFAULT nextval('crm."Projects_id_seq"'::regclass);


--
-- Name: Task_templates id; Type: DEFAULT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Task_templates" ALTER COLUMN id SET DEFAULT nextval('crm."Task_templates_id_seq"'::regclass);


--
-- Name: Tasks id; Type: DEFAULT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Tasks" ALTER COLUMN id SET DEFAULT nextval('crm."Tasks_id_seq"'::regclass);


--
-- Name: Testimonials id; Type: DEFAULT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Testimonials" ALTER COLUMN id SET DEFAULT nextval('crm."Testimonials_id_seq"'::regclass);


--
-- Name: Activities Activities_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Activities"
    ADD CONSTRAINT "Activities_pkey" PRIMARY KEY (id);


--
-- Name: Assesments Assesments_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Assesments"
    ADD CONSTRAINT "Assesments_pkey" PRIMARY KEY (id);


--
-- Name: Companies Companies_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Companies"
    ADD CONSTRAINT "Companies_pkey" PRIMARY KEY (id);


--
-- Name: Leads Leads_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Leads"
    ADD CONSTRAINT "Leads_pkey" PRIMARY KEY (id);


--
-- Name: Meetings Meetings_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Meetings"
    ADD CONSTRAINT "Meetings_pkey" PRIMARY KEY (id);


--
-- Name: Offer_templates Offer_templates_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Offer_templates"
    ADD CONSTRAINT "Offer_templates_pkey" PRIMARY KEY (id);


--
-- Name: Offers Offers_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Offers"
    ADD CONSTRAINT "Offers_pkey" PRIMARY KEY (id);


--
-- Name: Participants Participants_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Participants"
    ADD CONSTRAINT "Participants_pkey" PRIMARY KEY (id);


--
-- Name: Projects Projects_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Projects"
    ADD CONSTRAINT "Projects_pkey" PRIMARY KEY (id);


--
-- Name: Task_templates Task_templates_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Task_templates"
    ADD CONSTRAINT "Task_templates_pkey" PRIMARY KEY (id);


--
-- Name: Tasks Tasks_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Tasks"
    ADD CONSTRAINT "Tasks_pkey" PRIMARY KEY (id);


--
-- Name: Testimonials Testimonials_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."Testimonials"
    ADD CONSTRAINT "Testimonials_pkey" PRIMARY KEY (id);


--
-- Name: _nc_m2m_Activities_Leads _nc_m2m_Activities_Leads_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Activities_Leads"
    ADD CONSTRAINT "_nc_m2m_Activities_Leads_pkey" PRIMARY KEY ("Leads_id", "Activities_id");


--
-- Name: _nc_m2m_Activities_Meetings _nc_m2m_Activities_Meetings_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Activities_Meetings"
    ADD CONSTRAINT "_nc_m2m_Activities_Meetings_pkey" PRIMARY KEY ("Meetings_id", "Activities_id");


--
-- Name: _nc_m2m_Activities_Tasks _nc_m2m_Activities_Tasks_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Activities_Tasks"
    ADD CONSTRAINT "_nc_m2m_Activities_Tasks_pkey" PRIMARY KEY ("Tasks_id", "Activities_id");


--
-- Name: _nc_m2m_Assesments_Participants _nc_m2m_Assesments_Participants_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Assesments_Participants"
    ADD CONSTRAINT "_nc_m2m_Assesments_Participants_pkey" PRIMARY KEY ("Participants_id", "Assesments_id");


--
-- Name: _nc_m2m_Companies_Leads _nc_m2m_Companies_Leads_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Companies_Leads"
    ADD CONSTRAINT "_nc_m2m_Companies_Leads_pkey" PRIMARY KEY ("Leads_id", "Companies_id");


--
-- Name: _nc_m2m_Companies_Participants _nc_m2m_Companies_Participants_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Companies_Participants"
    ADD CONSTRAINT "_nc_m2m_Companies_Participants_pkey" PRIMARY KEY ("Participants_id", "Companies_id");


--
-- Name: _nc_m2m_Leads_Leads _nc_m2m_Leads_Leads_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Leads_Leads"
    ADD CONSTRAINT "_nc_m2m_Leads_Leads_pkey" PRIMARY KEY ("Leads1_id", "Leads_id");


--
-- Name: _nc_m2m_Leads_Meetings _nc_m2m_Leads_Meetings_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Leads_Meetings"
    ADD CONSTRAINT "_nc_m2m_Leads_Meetings_pkey" PRIMARY KEY ("Meetings_id", "Leads_id");


--
-- Name: _nc_m2m_Leads_Participants _nc_m2m_Leads_Participants_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Leads_Participants"
    ADD CONSTRAINT "_nc_m2m_Leads_Participants_pkey" PRIMARY KEY ("Participants_id", "Leads_id");


--
-- Name: _nc_m2m_Leads_Tasks _nc_m2m_Leads_Tasks_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Leads_Tasks"
    ADD CONSTRAINT "_nc_m2m_Leads_Tasks_pkey" PRIMARY KEY ("Tasks_id", "Leads_id");


--
-- Name: _nc_m2m_Leads_Testimonials _nc_m2m_Leads_Testimonials_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Leads_Testimonials"
    ADD CONSTRAINT "_nc_m2m_Leads_Testimonials_pkey" PRIMARY KEY ("Testimonials_id", "Leads_id");


--
-- Name: _nc_m2m_Offers_Leads _nc_m2m_Offers_Leads_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Offers_Leads"
    ADD CONSTRAINT "_nc_m2m_Offers_Leads_pkey" PRIMARY KEY ("Leads_id", "Offers_id");


--
-- Name: _nc_m2m_Participants_Meetings _nc_m2m_Participants_Meetings_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Participants_Meetings"
    ADD CONSTRAINT "_nc_m2m_Participants_Meetings_pkey" PRIMARY KEY ("Meetings_id", "Participants_id");


--
-- Name: _nc_m2m_Task_templates_Projects _nc_m2m_Task_templates_Projects_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Task_templates_Projects"
    ADD CONSTRAINT "_nc_m2m_Task_templates_Projects_pkey" PRIMARY KEY ("Projects_id", "Task_templates_id");


--
-- Name: _nc_m2m_Tasks_Projects _nc_m2m_Tasks_Projects_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Tasks_Projects"
    ADD CONSTRAINT "_nc_m2m_Tasks_Projects_pkey" PRIMARY KEY ("Projects_id", "Tasks_id");


--
-- Name: _nc_m2m_Tasks_Task_templates _nc_m2m_Tasks_Task_templates_pkey; Type: CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Tasks_Task_templates"
    ADD CONSTRAINT "_nc_m2m_Tasks_Task_templates_pkey" PRIMARY KEY ("Task_templates_id", "Tasks_id");


--
-- Name: Activities_order_idx; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "Activities_order_idx" ON crm."Activities" USING btree (nc_order);


--
-- Name: Assesments_order_idx; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "Assesments_order_idx" ON crm."Assesments" USING btree (nc_order);


--
-- Name: Companies_order_idx; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "Companies_order_idx" ON crm."Companies" USING btree (nc_order);


--
-- Name: Leads_order_idx; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "Leads_order_idx" ON crm."Leads" USING btree (nc_order);


--
-- Name: Meetings_order_idx; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "Meetings_order_idx" ON crm."Meetings" USING btree (nc_order);


--
-- Name: Offer_templates_order_idx; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "Offer_templates_order_idx" ON crm."Offer_templates" USING btree (nc_order);


--
-- Name: Offers_order_idx; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "Offers_order_idx" ON crm."Offers" USING btree (nc_order);


--
-- Name: Participants_order_idx; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "Participants_order_idx" ON crm."Participants" USING btree (nc_order);


--
-- Name: Projects_order_idx; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "Projects_order_idx" ON crm."Projects" USING btree (nc_order);


--
-- Name: Task_templates_order_idx; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "Task_templates_order_idx" ON crm."Task_templates" USING btree (nc_order);


--
-- Name: Tasks_order_idx; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "Tasks_order_idx" ON crm."Tasks" USING btree (nc_order);


--
-- Name: Testimonials_order_idx; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "Testimonials_order_idx" ON crm."Testimonials" USING btree (nc_order);


--
-- Name: fk_Activities_Leads_00ik6_2fyc; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Activities_Leads_00ik6_2fyc" ON crm."_nc_m2m_Activities_Leads" USING btree ("Leads_id");


--
-- Name: fk_Activities_Leads_bnddx7oaif; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Activities_Leads_bnddx7oaif" ON crm."_nc_m2m_Activities_Leads" USING btree ("Activities_id");


--
-- Name: fk_Activities_Meetings_q7uf0eakh8; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Activities_Meetings_q7uf0eakh8" ON crm."_nc_m2m_Activities_Meetings" USING btree ("Activities_id");


--
-- Name: fk_Activities_Meetings_v6n7hrtvsg; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Activities_Meetings_v6n7hrtvsg" ON crm."_nc_m2m_Activities_Meetings" USING btree ("Meetings_id");


--
-- Name: fk_Activities_Tasks_b1xsqr_mkj; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Activities_Tasks_b1xsqr_mkj" ON crm."_nc_m2m_Activities_Tasks" USING btree ("Activities_id");


--
-- Name: fk_Activities_Tasks_zk1y4st3no; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Activities_Tasks_zk1y4st3no" ON crm."_nc_m2m_Activities_Tasks" USING btree ("Tasks_id");


--
-- Name: fk_Assesments_Participan_o_pnjnuph1; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Assesments_Participan_o_pnjnuph1" ON crm."_nc_m2m_Assesments_Participants" USING btree ("Participants_id");


--
-- Name: fk_Assesments_Participan_pv80z1_038; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Assesments_Participan_pv80z1_038" ON crm."_nc_m2m_Assesments_Participants" USING btree ("Assesments_id");


--
-- Name: fk_Companies_Leads_1jucglsje4; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Companies_Leads_1jucglsje4" ON crm."_nc_m2m_Companies_Leads" USING btree ("Companies_id");


--
-- Name: fk_Companies_Leads_ml28m0rdpq; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Companies_Leads_ml28m0rdpq" ON crm."_nc_m2m_Companies_Leads" USING btree ("Leads_id");


--
-- Name: fk_Companies_Participan_usm9k2p87u; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Companies_Participan_usm9k2p87u" ON crm."_nc_m2m_Companies_Participants" USING btree ("Participants_id");


--
-- Name: fk_Companies_Participan_zgok0hwcdi; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Companies_Participan_zgok0hwcdi" ON crm."_nc_m2m_Companies_Participants" USING btree ("Companies_id");


--
-- Name: fk_Leads_Leads__3av5dhg_u; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Leads_Leads__3av5dhg_u" ON crm."_nc_m2m_Leads_Leads" USING btree ("Leads_id");


--
-- Name: fk_Leads_Leads_xm7w0tzgqe; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Leads_Leads_xm7w0tzgqe" ON crm."_nc_m2m_Leads_Leads" USING btree ("Leads1_id");


--
-- Name: fk_Leads_Meetings_4n8i_oqtp5; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Leads_Meetings_4n8i_oqtp5" ON crm."_nc_m2m_Leads_Meetings" USING btree ("Meetings_id");


--
-- Name: fk_Leads_Meetings_m5nz7fikl7; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Leads_Meetings_m5nz7fikl7" ON crm."_nc_m2m_Leads_Meetings" USING btree ("Leads_id");


--
-- Name: fk_Leads_Participan_2n_hgvpj0o; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Leads_Participan_2n_hgvpj0o" ON crm."_nc_m2m_Leads_Participants" USING btree ("Participants_id");


--
-- Name: fk_Leads_Participan_b30jtf_q67; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Leads_Participan_b30jtf_q67" ON crm."_nc_m2m_Leads_Participants" USING btree ("Leads_id");


--
-- Name: fk_Leads_Tasks_3dju40g7aq; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Leads_Tasks_3dju40g7aq" ON crm."_nc_m2m_Leads_Tasks" USING btree ("Leads_id");


--
-- Name: fk_Leads_Tasks_tpw4_q_btf; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Leads_Tasks_tpw4_q_btf" ON crm."_nc_m2m_Leads_Tasks" USING btree ("Tasks_id");


--
-- Name: fk_Leads_Testimonia_0pva62p8c9; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Leads_Testimonia_0pva62p8c9" ON crm."_nc_m2m_Leads_Testimonials" USING btree ("Testimonials_id");


--
-- Name: fk_Leads_Testimonia_lfa4srxrsi; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Leads_Testimonia_lfa4srxrsi" ON crm."_nc_m2m_Leads_Testimonials" USING btree ("Leads_id");


--
-- Name: fk_Offers_Leads_upid_2odni; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Offers_Leads_upid_2odni" ON crm."_nc_m2m_Offers_Leads" USING btree ("Leads_id");


--
-- Name: fk_Offers_Leads_uwswp7qymr; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Offers_Leads_uwswp7qymr" ON crm."_nc_m2m_Offers_Leads" USING btree ("Offers_id");


--
-- Name: fk_Participan_Meetings_9hsz1dsnpl; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Participan_Meetings_9hsz1dsnpl" ON crm."_nc_m2m_Participants_Meetings" USING btree ("Meetings_id");


--
-- Name: fk_Participan_Meetings_zwj5nxxy_t; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Participan_Meetings_zwj5nxxy_t" ON crm."_nc_m2m_Participants_Meetings" USING btree ("Participants_id");


--
-- Name: fk_Task_templ_Projects__j_aeunvtd; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Task_templ_Projects__j_aeunvtd" ON crm."_nc_m2m_Task_templates_Projects" USING btree ("Projects_id");


--
-- Name: fk_Task_templ_Projects_xj1br125vg; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Task_templ_Projects_xj1br125vg" ON crm."_nc_m2m_Task_templates_Projects" USING btree ("Task_templates_id");


--
-- Name: fk_Tasks_Projects_aj5bjcxt84; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Tasks_Projects_aj5bjcxt84" ON crm."_nc_m2m_Tasks_Projects" USING btree ("Tasks_id");


--
-- Name: fk_Tasks_Projects_bfospyvsg6; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Tasks_Projects_bfospyvsg6" ON crm."_nc_m2m_Tasks_Projects" USING btree ("Projects_id");


--
-- Name: fk_Tasks_Task_templ_767ifxy7yr; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Tasks_Task_templ_767ifxy7yr" ON crm."_nc_m2m_Tasks_Task_templates" USING btree ("Task_templates_id");


--
-- Name: fk_Tasks_Task_templ_xbfoa1igmw; Type: INDEX; Schema: crm; Owner: nocodb_crm_user
--

CREATE INDEX "fk_Tasks_Task_templ_xbfoa1igmw" ON crm."_nc_m2m_Tasks_Task_templates" USING btree ("Tasks_id");


--
-- Name: _nc_m2m_Activities_Leads fk_Activities_Leads_4mew9iul8j; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Activities_Leads"
    ADD CONSTRAINT "fk_Activities_Leads_4mew9iul8j" FOREIGN KEY ("Activities_id") REFERENCES crm."Activities"(id);


--
-- Name: _nc_m2m_Activities_Leads fk_Activities_Leads_srnm2qx3qs; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Activities_Leads"
    ADD CONSTRAINT "fk_Activities_Leads_srnm2qx3qs" FOREIGN KEY ("Leads_id") REFERENCES crm."Leads"(id);


--
-- Name: _nc_m2m_Activities_Meetings fk_Activities_Meetings_1zb1drzhft; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Activities_Meetings"
    ADD CONSTRAINT "fk_Activities_Meetings_1zb1drzhft" FOREIGN KEY ("Meetings_id") REFERENCES crm."Meetings"(id);


--
-- Name: _nc_m2m_Activities_Meetings fk_Activities_Meetings_ep9qxnchvl; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Activities_Meetings"
    ADD CONSTRAINT "fk_Activities_Meetings_ep9qxnchvl" FOREIGN KEY ("Activities_id") REFERENCES crm."Activities"(id);


--
-- Name: _nc_m2m_Activities_Tasks fk_Activities_Tasks_de0a0vme9x; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Activities_Tasks"
    ADD CONSTRAINT "fk_Activities_Tasks_de0a0vme9x" FOREIGN KEY ("Activities_id") REFERENCES crm."Activities"(id);


--
-- Name: _nc_m2m_Activities_Tasks fk_Activities_Tasks_y_dt0h1lsw; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Activities_Tasks"
    ADD CONSTRAINT "fk_Activities_Tasks_y_dt0h1lsw" FOREIGN KEY ("Tasks_id") REFERENCES crm."Tasks"(id);


--
-- Name: _nc_m2m_Assesments_Participants fk_Assesments_Participan_9wkmhle3jy; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Assesments_Participants"
    ADD CONSTRAINT "fk_Assesments_Participan_9wkmhle3jy" FOREIGN KEY ("Participants_id") REFERENCES crm."Participants"(id);


--
-- Name: _nc_m2m_Assesments_Participants fk_Assesments_Participan_x7jqr9c44q; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Assesments_Participants"
    ADD CONSTRAINT "fk_Assesments_Participan_x7jqr9c44q" FOREIGN KEY ("Assesments_id") REFERENCES crm."Assesments"(id);


--
-- Name: _nc_m2m_Companies_Leads fk_Companies_Leads_g4iks2bzz8; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Companies_Leads"
    ADD CONSTRAINT "fk_Companies_Leads_g4iks2bzz8" FOREIGN KEY ("Companies_id") REFERENCES crm."Companies"(id);


--
-- Name: _nc_m2m_Companies_Leads fk_Companies_Leads_ks8ktkrh4u; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Companies_Leads"
    ADD CONSTRAINT "fk_Companies_Leads_ks8ktkrh4u" FOREIGN KEY ("Leads_id") REFERENCES crm."Leads"(id);


--
-- Name: _nc_m2m_Companies_Participants fk_Companies_Participan_u37a84lq_l; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Companies_Participants"
    ADD CONSTRAINT "fk_Companies_Participan_u37a84lq_l" FOREIGN KEY ("Participants_id") REFERENCES crm."Participants"(id);


--
-- Name: _nc_m2m_Companies_Participants fk_Companies_Participan_u50vpcm989; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Companies_Participants"
    ADD CONSTRAINT "fk_Companies_Participan_u50vpcm989" FOREIGN KEY ("Companies_id") REFERENCES crm."Companies"(id);


--
-- Name: _nc_m2m_Leads_Leads fk_Leads_Leads_4g986laner; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Leads_Leads"
    ADD CONSTRAINT "fk_Leads_Leads_4g986laner" FOREIGN KEY ("Leads_id") REFERENCES crm."Leads"(id);


--
-- Name: _nc_m2m_Leads_Leads fk_Leads_Leads_pop5sf2z3x; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Leads_Leads"
    ADD CONSTRAINT "fk_Leads_Leads_pop5sf2z3x" FOREIGN KEY ("Leads1_id") REFERENCES crm."Leads"(id);


--
-- Name: _nc_m2m_Leads_Meetings fk_Leads_Meetings_i3d4jpt4x_; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Leads_Meetings"
    ADD CONSTRAINT "fk_Leads_Meetings_i3d4jpt4x_" FOREIGN KEY ("Leads_id") REFERENCES crm."Leads"(id);


--
-- Name: _nc_m2m_Leads_Meetings fk_Leads_Meetings_keez4s88pg; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Leads_Meetings"
    ADD CONSTRAINT "fk_Leads_Meetings_keez4s88pg" FOREIGN KEY ("Meetings_id") REFERENCES crm."Meetings"(id);


--
-- Name: _nc_m2m_Leads_Participants fk_Leads_Participan_ewbrp4exwo; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Leads_Participants"
    ADD CONSTRAINT "fk_Leads_Participan_ewbrp4exwo" FOREIGN KEY ("Leads_id") REFERENCES crm."Leads"(id);


--
-- Name: _nc_m2m_Leads_Participants fk_Leads_Participan_nz98v46jjr; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Leads_Participants"
    ADD CONSTRAINT "fk_Leads_Participan_nz98v46jjr" FOREIGN KEY ("Participants_id") REFERENCES crm."Participants"(id);


--
-- Name: _nc_m2m_Leads_Tasks fk_Leads_Tasks_k8chah_12m; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Leads_Tasks"
    ADD CONSTRAINT "fk_Leads_Tasks_k8chah_12m" FOREIGN KEY ("Leads_id") REFERENCES crm."Leads"(id);


--
-- Name: _nc_m2m_Leads_Tasks fk_Leads_Tasks_n9v4mlhayx; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Leads_Tasks"
    ADD CONSTRAINT "fk_Leads_Tasks_n9v4mlhayx" FOREIGN KEY ("Tasks_id") REFERENCES crm."Tasks"(id);


--
-- Name: _nc_m2m_Leads_Testimonials fk_Leads_Testimonia_l3jqm62wbg; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Leads_Testimonials"
    ADD CONSTRAINT "fk_Leads_Testimonia_l3jqm62wbg" FOREIGN KEY ("Leads_id") REFERENCES crm."Leads"(id);


--
-- Name: _nc_m2m_Leads_Testimonials fk_Leads_Testimonia_rj_5bjba7y; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Leads_Testimonials"
    ADD CONSTRAINT "fk_Leads_Testimonia_rj_5bjba7y" FOREIGN KEY ("Testimonials_id") REFERENCES crm."Testimonials"(id);


--
-- Name: _nc_m2m_Offers_Leads fk_Offers_Leads__zdwa35779; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Offers_Leads"
    ADD CONSTRAINT "fk_Offers_Leads__zdwa35779" FOREIGN KEY ("Offers_id") REFERENCES crm."Offers"(id);


--
-- Name: _nc_m2m_Offers_Leads fk_Offers_Leads_jypie2jkmz; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Offers_Leads"
    ADD CONSTRAINT "fk_Offers_Leads_jypie2jkmz" FOREIGN KEY ("Leads_id") REFERENCES crm."Leads"(id);


--
-- Name: _nc_m2m_Participants_Meetings fk_Participan_Meetings_abw63e4w96; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Participants_Meetings"
    ADD CONSTRAINT "fk_Participan_Meetings_abw63e4w96" FOREIGN KEY ("Participants_id") REFERENCES crm."Participants"(id);


--
-- Name: _nc_m2m_Participants_Meetings fk_Participan_Meetings_ifehki2qfm; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Participants_Meetings"
    ADD CONSTRAINT "fk_Participan_Meetings_ifehki2qfm" FOREIGN KEY ("Meetings_id") REFERENCES crm."Meetings"(id);


--
-- Name: _nc_m2m_Task_templates_Projects fk_Task_templ_Projects_1078eiuwzk; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Task_templates_Projects"
    ADD CONSTRAINT "fk_Task_templ_Projects_1078eiuwzk" FOREIGN KEY ("Task_templates_id") REFERENCES crm."Task_templates"(id);


--
-- Name: _nc_m2m_Task_templates_Projects fk_Task_templ_Projects_uy7vuratrz; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Task_templates_Projects"
    ADD CONSTRAINT "fk_Task_templ_Projects_uy7vuratrz" FOREIGN KEY ("Projects_id") REFERENCES crm."Projects"(id);


--
-- Name: _nc_m2m_Tasks_Projects fk_Tasks_Projects_rwowcl9fnp; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Tasks_Projects"
    ADD CONSTRAINT "fk_Tasks_Projects_rwowcl9fnp" FOREIGN KEY ("Projects_id") REFERENCES crm."Projects"(id);


--
-- Name: _nc_m2m_Tasks_Projects fk_Tasks_Projects_wh62or7v3_; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Tasks_Projects"
    ADD CONSTRAINT "fk_Tasks_Projects_wh62or7v3_" FOREIGN KEY ("Tasks_id") REFERENCES crm."Tasks"(id);


--
-- Name: _nc_m2m_Tasks_Task_templates fk_Tasks_Task_templ_3maxjbpmfx; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Tasks_Task_templates"
    ADD CONSTRAINT "fk_Tasks_Task_templ_3maxjbpmfx" FOREIGN KEY ("Task_templates_id") REFERENCES crm."Task_templates"(id);


--
-- Name: _nc_m2m_Tasks_Task_templates fk_Tasks_Task_templ_g3tvy1ug_z; Type: FK CONSTRAINT; Schema: crm; Owner: nocodb_crm_user
--

ALTER TABLE ONLY crm."_nc_m2m_Tasks_Task_templates"
    ADD CONSTRAINT "fk_Tasks_Task_templ_g3tvy1ug_z" FOREIGN KEY ("Tasks_id") REFERENCES crm."Tasks"(id);


--
-- Name: SCHEMA crm; Type: ACL; Schema: -; Owner: postgres
--

GRANT ALL ON SCHEMA crm TO nocodb_crm_user;


--
-- PostgreSQL database dump complete
--

\unrestrict 5qesuY6nM5uDuhQY5OvWU8SZXxeApZhDJL75OphymP2IEjgdVZyjEbkbgObTPdl

