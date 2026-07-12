-- ============================================================================
-- CoAction CRM — dane demo/testowe do FAZY 3 (Offer Builder w NocoDB)
-- Usage:  psql --username appdata_owner --dbname appdata < ./seed_demo.sql
--         (PO docker/schema.sql i docker/seed.sql — potrzebuje pricing_tiers/users)
--
-- To NIE są dane referencyjne (patrz seed.sql) — to jednorazowy fixture
-- potrzebny do: (a) mieć wiersz do otwarcia w widoku crm.v_offer_builder w
-- NocoDB (widok wspiera tylko SELECT/UPDATE, nie INSERT), (b) test pętli
-- cenowej 60h→45h z IMPLEMENTATION_PLAN.md FAZA 3 pkt 4. Do usunięcia albo
-- pozostawienia jako dane demo — decyzja przed produkcją (FAZA 6).
--
-- Re-runnable: usuwa poprzedni demo-rekord po organizations.name przed
-- ponownym insertem (analogicznie do testimonials w seed.sql).
-- ============================================================================

DO $$
DECLARE
    v_org_id            bigint;
    v_person_id         bigint;
    v_client_id         bigint;
    v_opportunity_id    bigint;
    v_participant_id    bigint;
    v_audit_id          bigint;
    v_recommendation_id bigint;
    v_offer_id          bigint;
    v_sales_user_id     bigint;
    v_auditor_user_id   bigint;
    v_tier_60h          bigint;
    v_tier_15h_group    bigint;
BEGIN
    -- cleanup poprzedniego demo runu (idempotencja) -----------------------------
    SELECT id INTO v_org_id FROM appdata.organizations WHERE name = 'Demo Sp. z o.o.';
    IF v_org_id IS NOT NULL THEN
        DELETE FROM appdata.offer_items WHERE offer_id IN (
            SELECT off.id FROM appdata.offers off
            JOIN appdata.opportunities o ON o.id = off.opportunity_id
            JOIN appdata.clients c ON c.id = o.client_id
            WHERE c.organization_id = v_org_id
        );
        DELETE FROM appdata.offers WHERE opportunity_id IN (
            SELECT o.id FROM appdata.opportunities o
            JOIN appdata.clients c ON c.id = o.client_id
            WHERE c.organization_id = v_org_id
        );
        DELETE FROM appdata.recommendation_goals WHERE recommendation_id IN (
            SELECT rec.id FROM appdata.recommendations rec
            JOIN appdata.opportunities o ON o.id = rec.opportunity_id
            JOIN appdata.clients c ON c.id = o.client_id
            WHERE c.organization_id = v_org_id
        );
        DELETE FROM appdata.recommendations WHERE opportunity_id IN (
            SELECT o.id FROM appdata.opportunities o
            JOIN appdata.clients c ON c.id = o.client_id
            WHERE c.organization_id = v_org_id
        );
        DELETE FROM appdata.audit_scores WHERE audit_id IN (
            SELECT a.id FROM appdata.audits a
            JOIN appdata.opportunities o ON o.id = a.opportunity_id
            JOIN appdata.clients c ON c.id = o.client_id
            WHERE c.organization_id = v_org_id
        );
        DELETE FROM appdata.audits WHERE opportunity_id IN (
            SELECT o.id FROM appdata.opportunities o
            JOIN appdata.clients c ON c.id = o.client_id
            WHERE c.organization_id = v_org_id
        );
        DELETE FROM appdata.participants WHERE client_id IN (
            SELECT id FROM appdata.clients WHERE organization_id = v_org_id
        );
        DELETE FROM appdata.opportunity_stage_history WHERE opportunity_id IN (
            SELECT o.id FROM appdata.opportunities o
            JOIN appdata.clients c ON c.id = o.client_id
            WHERE c.organization_id = v_org_id
        );
        DELETE FROM appdata.opportunities WHERE client_id IN (
            SELECT id FROM appdata.clients WHERE organization_id = v_org_id
        );
        DELETE FROM appdata.clients WHERE organization_id = v_org_id;
        DELETE FROM appdata.people WHERE organization_id = v_org_id;
        DELETE FROM appdata.organizations WHERE id = v_org_id;
    END IF;

    -- lookupy na dane zasiane przez seed.sql -------------------------------------
    SELECT id INTO v_sales_user_id   FROM appdata.users WHERE email = 'p.fidzina@coaction.pl';
    SELECT id INTO v_auditor_user_id FROM appdata.users WHERE email = 'd.michalska@coaction.pl';
    SELECT id INTO v_tier_60h        FROM appdata.pricing_tiers WHERE product = 'Business English 1:1' AND hours = 60 AND format = '1-1';
    SELECT id INTO v_tier_15h_group  FROM appdata.pricing_tiers WHERE product = 'Warsztat grupowy'      AND hours = 15 AND format = 'group';

    IF v_sales_user_id IS NULL OR v_auditor_user_id IS NULL OR v_tier_60h IS NULL OR v_tier_15h_group IS NULL THEN
        RAISE EXCEPTION 'seed_demo.sql: brakujące dane z seed.sql — uruchom najpierw app_seed.sh';
    END IF;

    -- rdzeń: organizacja → osoba → klient → szansa -------------------------------
    INSERT INTO appdata.organizations (name, industry, size_bucket)
    VALUES ('Demo Sp. z o.o.', 'IT', '50-250')
    RETURNING id INTO v_org_id;

    INSERT INTO appdata.people (organization_id, first_name, last_name, email, job_title)
    VALUES (v_org_id, 'Jan', 'Kowalski', 'jan.kowalski@demo-fixture.local', 'Head of Engineering')
    RETURNING id INTO v_person_id;

    INSERT INTO appdata.clients (type, organization_id, primary_contact_id, owner_user_id, source, contact_form, qualification)
    VALUES ('B2B', v_org_id, v_person_id, v_sales_user_id, 'referral', 'booking', 'SQL')
    RETURNING id INTO v_client_id;

    INSERT INTO appdata.opportunities (client_id, stage, state, value_pln, label)
    VALUES (v_client_id, 'przygotowanie_oferty', 'otwarta', 16800.00, 'Demo — Business English dla zespołu inżynierskiego')
    RETURNING id INTO v_opportunity_id;

    -- audyt + 5 wymiarów CEFR -----------------------------------------------------
    INSERT INTO appdata.participants (client_id, person_id, manager_needs)
    VALUES (v_client_id, v_person_id, 'Swobodna komunikacja techniczna z klientami US.')
    RETURNING id INTO v_participant_id;

    INSERT INTO appdata.audits (participant_id, opportunity_id, auditor_user_id, conducted_at, status)
    VALUES (v_participant_id, v_opportunity_id, v_auditor_user_id, now() - interval '3 days', 'done')
    RETURNING id INTO v_audit_id;

    INSERT INTO appdata.audit_scores (audit_id, dimension, cefr_level, cefr_decimal) VALUES
        (v_audit_id, 'overall',           'B2', 0.6),
        (v_audit_id, 'range',             'B2', 0.4),
        (v_audit_id, 'accuracy',          'B1', 0.8),
        (v_audit_id, 'fluency',           'B2', 0.2),
        (v_audit_id, 'communicativeness', 'C1', 0.0);

    -- rekomendacja + cele szkoleniowe ---------------------------------------------
    INSERT INTO appdata.recommendations (opportunity_id, audit_id, type, headline, situation_description, approved_by, approved_at)
    VALUES (
        v_opportunity_id, v_audit_id, 'business_english',
        'Business English 1:1 dla zespołu inżynierskiego',
        'Zespół komunikuje się głównie pisemnie, brakuje pewności w rozmowach na żywo z klientami US.',
        v_sales_user_id, now() - interval '1 day'
    )
    RETURNING id INTO v_recommendation_id;

    INSERT INTO appdata.recommendation_goals (recommendation_id, position, title, body, stage_label) VALUES
        (v_recommendation_id, 1, 'Pewność w rozmowach technicznych', 'Swobodne prowadzenie code review i demo w j. angielskim.', 'Miesiąc 1-2'),
        (v_recommendation_id, 2, 'Komunikacja z klientem',           'Samodzielne prowadzenie calli statusowych z klientem US.', 'Miesiąc 3-4');

    -- oferta (draft) + 2 pozycje ----------------------------------------------------
    INSERT INTO appdata.offers (opportunity_id, recommendation_id, status, discount_pct, valid_until, created_by)
    VALUES (v_opportunity_id, v_recommendation_id, 'draft', 0, CURRENT_DATE + 30, v_sales_user_id)
    RETURNING id INTO v_offer_id;

    INSERT INTO appdata.offer_items (offer_id, position, product, label, hours, format, pricing_tier_id) VALUES
        (v_offer_id, 1, 'Business English 1:1', 'Trening indywidualny', 60, '1-1',   v_tier_60h),
        (v_offer_id, 2, 'Warsztat grupowy',      'Warsztat zespołowy',   15, 'group', v_tier_15h_group);

    RAISE NOTICE 'seed_demo.sql: offer_id=%, opportunity_id=%, total powinno być trigger-owo 75h / 20400.00 PLN', v_offer_id, v_opportunity_id;
END $$;
