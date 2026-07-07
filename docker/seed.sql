-- ============================================================================
-- CoAction seed data (v2): 5 walkthrough scenarios
-- Load AFTER schema.sql into a clean database:
--   psql -U <user> -d coaction_db -f seed.sql
--
-- Scenarios:
--   1. Jedrzej   - B2C, discovery + demo (draft presented), offer v2 sent
--   2. Patrycja  - B2C, buys for herself + Piotr, shared demo, no adjustments
--                  needed, offer v1 sent, currently being DISCUSSED
--   3. Ola (CEO) - B2B, 5 employees (Ola is contact only, NOT a participant),
--                  discovery + 2 audits, offer v1 superseded by v2, WON (signed)
--   4. Janusz    - B2B, 2 employees, discovery + 3 audits (Iwona audited twice),
--                  offer rejected, deal LOST (budget cut, note kept)
--   5. Spam lead - DISQUALIFIED at qualification (exercises the new guard)
--
-- IDs are explicit (OVERRIDING SYSTEM VALUE) for readability; sequences are
-- realigned at the end so future inserts don't collide.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- Team + n8n bot (id 5 is the actor for automated changes)
-- ----------------------------------------------------------------------------
INSERT INTO users (id, full_name, email, role) OVERRIDING SYSTEM VALUE VALUES
    (1, 'Przemek', 'przemek@coaction.example', 'sales'),
    (2, 'Dorota',  'dorota@coaction.example',  'methodologist_b2c'),
    (3, 'Basia',   'basia@coaction.example',   'methodologist_b2b'),
    (4, 'Kasia',   'kasia@coaction.example',   'reviewer'),
    (5, 'n8n Bot', 'n8n-bot@coaction.example', 'bot');

-- ----------------------------------------------------------------------------
-- Clients
-- ----------------------------------------------------------------------------
INSERT INTO clients (id, type, company_name, contact_first_name, contact_last_name,
                     contact_email, contact_phone, industry, company_size, lead_source, folder_url)
OVERRIDING SYSTEM VALUE VALUES
    (1, 'B2C', NULL, 'Jedrzej', 'Kowalski', 'jedrzej@example.com', '+48 600 100 100', NULL, NULL, 'form', 'https://drive.example/clients/jedrzej'),
    (2, 'B2C', NULL, 'Patrycja', 'Nowak', 'patrycja@example.com', '+48 600 200 200', NULL, NULL, 'form', 'https://drive.example/clients/patrycja'),
    (3, 'B2B', 'Olatech Sp. z o.o.', 'Ola', 'Wisniewska', 'ola@olatech.example', '+48 600 300 300', 'IT services', '50-100', 'referral', 'https://drive.example/clients/olatech'),
    (4, 'B2B', 'JanTrans Sp. z o.o.', 'Janusz', 'Mazur', 'janusz@jantrans.example', '+48 600 400 400', 'logistics', '20-50', 'email', 'https://drive.example/clients/jantrans'),
    (5, 'B2C', NULL, 'Zbigniew', 'Spamowski', 'zbig@spam.example', NULL, NULL, NULL, 'form', NULL);

-- ----------------------------------------------------------------------------
-- Deals
-- ----------------------------------------------------------------------------
INSERT INTO deals (id, client_id, title, variant, qualification, status, estimated_value,
                   disqualification_reason, lost_reason, lost_note, closed_at)
OVERRIDING SYSTEM VALUE VALUES
    (1, 1, 'Jedrzej Kowalski — B2C', 'B2C', 'SQL', 'offer_sent', 5000.00,
     NULL, NULL, NULL, NULL),
    (2, 2, 'Patrycja Nowak — B2C', 'B2C', 'MQL', 'offer_discussed', 10000.00,
     NULL, NULL, NULL, NULL),
    (3, 3, 'Olatech Sp. z o.o. — B2B', 'B2B_pre_discovery', 'SQL', 'won', 30000.00,
     NULL, NULL, NULL, now() - interval '2 days'),
    (4, 4, 'JanTrans Sp. z o.o. — B2B', 'B2B_pre_discovery', 'SQL', 'lost', 14000.00,
     NULL, 'budget', 'Janusz had to cut Q3 budget; interested in coming back in Q4 — follow up in October.',
     now() - interval '5 days'),
    (5, 5, 'Zbigniew Spamowski — B2C', 'B2C', NULL, 'disqualified', NULL,
     'Not the target group: looking for a free language exchange, no training need.', NULL, NULL,
     now() - interval '9 days');

-- ----------------------------------------------------------------------------
-- Deal status history (append-only; changed_by: 5 = n8n bot, others = humans)
-- ----------------------------------------------------------------------------
INSERT INTO deal_status_history (deal_id, status, changed_at, changed_by) VALUES
    -- Scenario 1: full B2C path up to offer_sent
    (1, 'new',            now() - interval '24 days', 5),
    (1, 'qualified',      now() - interval '23 days', 5),
    (1, 'discovery',      now() - interval '22 days', 5),
    (1, 'analysis',       now() - interval '20 days', 5),
    (1, 'recommendation', now() - interval '18 days', 5),
    (1, 'demo',           now() - interval '16 days', 5),
    (1, 'adjustment',     now() - interval '14 days', 5),
    (1, 'offer_sent',     now() - interval '12 days', 5),
    -- Scenario 2: no adjustment needed (optional stage skipped), now discussed
    (2, 'new',             now() - interval '21 days', 5),
    (2, 'qualified',       now() - interval '20 days', 5),
    (2, 'discovery',       now() - interval '19 days', 5),
    (2, 'analysis',        now() - interval '17 days', 5),
    (2, 'recommendation',  now() - interval '15 days', 5),
    (2, 'demo',            now() - interval '13 days', 5),
    (2, 'offer_sent',      now() - interval '11 days', 5),
    (2, 'offer_discussed', now() - interval '8 days',  5),
    -- Scenario 3: full B2B path to won (contract signed)
    (3, 'new',             now() - interval '35 days', 5),
    (3, 'qualified',       now() - interval '34 days', 5),
    (3, 'discovery',       now() - interval '31 days', 5),
    (3, 'analysis',        now() - interval '28 days', 5),
    (3, 'recommendation',  now() - interval '26 days', 5),   -- draft offer v1 before audits
    (3, 'audit',           now() - interval '25 days', 5),
    (3, 'adjustment',      now() - interval '12 days', 5),
    (3, 'offer_sent',      now() - interval '10 days', 5),
    (3, 'offer_discussed', now() - interval '7 days',  5),
    (3, 'contract_sent',   now() - interval '5 days',  5),
    (3, 'won',             now() - interval '2 days',  1),   -- Przemek moved the pipeline card
    -- Scenario 4: B2B lost after offer
    (4, 'new',            now() - interval '28 days', 5),
    (4, 'qualified',      now() - interval '27 days', 5),
    (4, 'discovery',      now() - interval '26 days', 5),
    (4, 'analysis',       now() - interval '23 days', 5),
    (4, 'recommendation', now() - interval '21 days', 5),   -- draft offer v1 before audits
    (4, 'audit',          now() - interval '20 days', 5),
    (4, 'offer_sent',     now() - interval '8 days',  5),
    (4, 'lost',           now() - interval '5 days',  1),    -- Przemek moved the card, reason task followed
    -- Scenario 5: disqualified early
    (5, 'new',          now() - interval '10 days', 5),
    (5, 'disqualified', now() - interval '9 days',  1);

-- ----------------------------------------------------------------------------
-- Participants
-- Note: Ola (client 3 contact) and Janusz (client 4 contact) are NOT participants.
-- ----------------------------------------------------------------------------
INSERT INTO participants (id, client_id, first_name, last_name, email, position,
                          self_assessed_level, communication_situations, source, verification_status)
OVERRIDING SYSTEM VALUE VALUES
    -- Scenario 1
    (1, 1, 'Jedrzej', 'Kowalski', 'jedrzej@example.com', 'Freelance designer', 'B1', 'client calls, e-mails', 'form', 'verified'),
    -- Scenario 2 (Piotr added manually via linked record after discovery)
    (2, 2, 'Patrycja', 'Nowak', 'patrycja@example.com', 'Product manager', 'B2', 'stakeholder meetings, presentations', 'form', 'verified'),
    (3, 2, 'Piotr', 'Nowak', 'piotr@example.com', 'Software developer', 'A2', 'daily standups, code reviews', 'manual', 'verified'),
    -- Scenario 3: 5 employees, drafted by AI from the discovery transcript, then verified
    (4, 3, 'Marek', 'Lis', 'marek@olatech.example', 'Sales manager', 'B1', 'client negotiations', 'ai_extraction', 'verified'),
    (5, 3, 'Anna', 'Zajac', 'anna@olatech.example', 'Support lead', 'A2', 'support tickets, calls', 'ai_extraction', 'verified'),
    (6, 3, 'Tomasz', 'Krol', 'tomasz@olatech.example', 'Backend developer', 'B1', 'technical documentation', 'ai_extraction', 'verified'),
    (7, 3, 'Ewa', 'Baran', 'ewa@olatech.example', 'HR specialist', 'A2', 'onboarding, internal comms', 'ai_extraction', 'verified'),
    (8, 3, 'Kamil', 'Duda', 'kamil@olatech.example', 'Project manager', 'B2', 'client status meetings', 'ai_extraction', 'verified'),
    -- Scenario 4: 2 employees
    (9, 4, 'Robert', 'Gajda', 'robert@jantrans.example', 'Dispatcher', 'A2', 'phone calls with foreign carriers', 'manual', 'verified'),
    (10, 4, 'Iwona', 'Szulc', 'iwona@jantrans.example', 'Forwarding specialist', 'A2', 'e-mails, transport documents', 'manual', 'verified');

-- ----------------------------------------------------------------------------
-- Meetings
-- B2C: discovery + demo (draft offer presented, participant assessed at demo)
-- B2B: discovery + N audits
-- ----------------------------------------------------------------------------
INSERT INTO meetings (id, deal_id, type, scheduled_at, booking_ref, attendees,
                      transcript, transcript_status, ai_extraction, notes)
OVERRIDING SYSTEM VALUE VALUES
    -- Scenario 1: discovery, then demo where the draft offer was presented
    (1, 1, 'discovery', now() - interval '22 days', 'bk-1001', 'Jedrzej, Przemek',
     '[transcript placeholder]', 'approved',
     '{"goals": ["confident client calls"], "challenges": ["speaking fluency"], "level_hint": "B1"}',
     NULL),
    (2, 1, 'demo', now() - interval '16 days', 'bk-1002', 'Jedrzej, Dorota',
     '[transcript placeholder]', 'approved', NULL,
     'Draft offer (v1) presented; Jedrzej asked to reduce 60h to 40h.'),
    -- Scenario 2: discovery, then one shared demo for both participants
    (3, 2, 'discovery', now() - interval '19 days', 'bk-1003', 'Patrycja, Przemek',
     '[transcript placeholder]', 'approved',
     '{"goals": ["presentations (Patrycja)", "daily communication (Piotr)"], "participants_mentioned": ["Piotr"]}',
     'Piotr mentioned during discovery; his participant record was added manually afterwards.'),
    (4, 2, 'demo', now() - interval '13 days', 'bk-1004', 'Patrycja, Piotr, Dorota',
     '[transcript placeholder]', 'approved', NULL,
     'Draft accepted as-is, no adjustments requested.'),
    -- Scenario 3: discovery with Ola + 2 audit meetings
    (5, 3, 'discovery', now() - interval '31 days', 'bk-1005', 'Ola (CEO), Przemek',
     '[transcript placeholder]', 'approved',
     '{"goals": ["client-facing English for 5 staff"], "participants_mentioned": ["Marek", "Anna", "Tomasz", "Ewa", "Kamil"], "business_context": "expansion to DACH market"}',
     NULL),
    (6, 3, 'audit', now() - interval '24 days', 'bk-1006', 'Marek, Anna, Tomasz, Basia',
     '[transcript placeholder]', 'approved', NULL, 'Group audit A: 3 participants'),
    (7, 3, 'audit', now() - interval '23 days', 'bk-1007', 'Ewa, Kamil, Basia',
     '[transcript placeholder]', 'approved', NULL, 'Group audit B: 2 participants'),
    -- Scenario 4: discovery with Janusz + 3 audits (Iwona audited twice)
    (8, 4, 'discovery', now() - interval '26 days', 'bk-1008', 'Janusz, Przemek',
     '[transcript placeholder]', 'approved',
     '{"goals": ["phone English for dispatch team"], "participants_mentioned": ["Robert", "Iwona"]}',
     NULL),
    (9, 4, 'audit', now() - interval '19 days', 'bk-1009', 'Robert, Basia',
     '[transcript placeholder]', 'approved', NULL, NULL),
    (10, 4, 'audit', now() - interval '18 days', 'bk-1010', 'Iwona, Basia',
     '[transcript placeholder]', 'approved', NULL, NULL),
    (11, 4, 'audit', now() - interval '13 days', 'bk-1011', 'Iwona, Basia',
     '[transcript placeholder]', 'approved', NULL,
     'Follow-up audit: first session was inconclusive on speaking fluency.');

-- ----------------------------------------------------------------------------
-- Audit results (one row = one participant evaluated in one meeting;
-- B2C evaluations happen at the demo, B2B at audits)
-- ----------------------------------------------------------------------------
INSERT INTO audit_results (id, meeting_id, participant_id, evaluated_by, language_level,
                           fluency, communicativeness, strengths, gaps, observations)
OVERRIDING SYSTEM VALUE VALUES
    -- Scenario 1: Dorota evaluated Jedrzej at the demo (meeting 2)
    (1, 2, 1, 2, 'B1', 'medium', 'good', 'good vocabulary range', 'hesitation in spontaneous speech', NULL),
    -- Scenario 2: shared demo (meeting 4), two evaluations
    (2, 4, 2, 2, 'B2', 'good', 'very good', 'confident presenter', 'advanced grammar accuracy', NULL),
    (3, 4, 3, 2, 'A2+', 'low', 'medium', 'motivated, good comprehension', 'speaking confidence, tenses', NULL),
    -- Scenario 3: Basia; results reference their audit meeting
    (4, 6, 4, 3, 'B1', 'medium', 'good', 'negotiation vocabulary', 'listening with native speakers', NULL),
    (5, 6, 5, 3, 'A2', 'low', 'medium', 'written support replies', 'phone call confidence', NULL),
    (6, 6, 6, 3, 'B1+', 'medium', 'good', 'technical vocabulary', 'small talk, meetings', NULL),
    (7, 7, 7, 3, 'A2', 'low', 'medium', 'reading comprehension', 'speaking overall', NULL),
    (8, 7, 8, 3, 'B2', 'good', 'very good', 'client meetings', 'nuanced negotiation language', NULL),
    -- Scenario 4: Iwona has TWO audit results (meetings 10 and 11)
    (9, 9, 9, 3, 'A2', 'low', 'medium', 'standard dispatch phrases', 'anything beyond routine calls', NULL),
    (10, 10, 10, 3, 'A2', 'low', 'low', 'document vocabulary', 'speaking fluency — needs follow-up', 'Inconclusive; second audit scheduled.'),
    (11, 11, 10, 3, 'A2+', 'medium', 'medium', 'improved under less stress', 'grammar accuracy', 'Follow-up confirmed A2+ working level.');

-- ----------------------------------------------------------------------------
-- Recommendations (always per participant; double FK: participant + deal)
-- The set of approved rows IS the content of the draft offer (v1).
-- ----------------------------------------------------------------------------
INSERT INTO recommendations (id, participant_id, deal_id, recommended_by, path_type,
                             justification, priority, proposed_hours, training_variant, status)
OVERRIDING SYSTEM VALUE VALUES
    -- Scenario 1: hours reduced 60 -> 40 after the demo (adjustment stage)
    (1, 1, 1, 2, 'business_english', 'Focus on fluency in client calls; reduced from 60h to 40h at client request', 'high', 40, 'individual', 'approved'),
    -- Scenario 2: different paths for each person
    (2, 2, 2, 2, 'english_plus_skills', 'Presentation skills on top of solid B2', 'medium', 30, 'individual', 'approved'),
    (3, 3, 2, 2, 'business_english', 'Core speaking confidence first', 'high', 60, 'individual', 'approved'),
    -- Scenario 3: 5 recommendations
    (4, 4, 3, 3, 'business_english', 'Negotiation-focused track', 'high', 50, 'group', 'approved'),
    (5, 5, 3, 3, 'business_english', 'Phone support track', 'high', 60, 'group', 'approved'),
    (6, 6, 3, 3, 'english_plus_skills', 'Meetings + small talk module', 'medium', 40, 'group', 'approved'),
    (7, 7, 3, 3, 'business_english', 'General speaking foundation', 'medium', 60, 'group', 'approved'),
    (8, 8, 3, 3, 'skills_only', 'Language level sufficient; negotiation skills workshop', 'low', 20, 'individual', 'approved'),
    -- Scenario 4: approved on merit, deal lost later (status stays approved — history)
    (9, 9, 4, 3, 'business_english', 'Routine-call breakout track', 'high', 50, 'group', 'approved'),
    (10, 10, 4, 3, 'business_english', 'Fluency-first track after follow-up audit', 'high', 50, 'group', 'approved');

-- ----------------------------------------------------------------------------
-- Offers (immutable rows; v1 draft = sketch shown to the client)
-- Rows are inserted with their final status to respect the immutability trigger
-- (in production n8n inserts as 'draft' and only ever updates the status column).
-- ----------------------------------------------------------------------------
INSERT INTO offers (id, deal_id, version, template_name, total_hours, price_net, currency,
                    recommendations_snapshot, included_sections, file_url, status, created_by)
OVERRIDING SYSTEM VALUE VALUES
    -- Scenario 1: v1 = 60h sketch presented at demo, v2 = 40h after adjustment, sent
    (1, 1, 1, 'b2c_individual', 60, 7800.00, 'PLN',
     '[{"recommendation_id": 1, "participant": "Jedrzej Kowalski", "path_type": "business_english", "hours": 60}]',
     '{"testimonials": ["b2c_freelancer_case"]}', 'https://files.example/offers/deal1-v1.pdf', 'superseded', 5),
    (2, 1, 2, 'b2c_individual', 40, 5200.00, 'PLN',
     '[{"recommendation_id": 1, "participant": "Jedrzej Kowalski", "path_type": "business_english", "hours": 40}]',
     '{"testimonials": ["b2c_freelancer_case"], "note": "hours reduced 60 -> 40 at client request after demo"}',
     'https://files.example/offers/deal1-v2.pdf', 'sent', 5),

    -- Scenario 2: draft accepted as-is at demo, v1 sent (no adjustment cycle)
    (3, 2, 1, 'b2c_individual', 90, 11700.00, 'PLN',
     '[{"recommendation_id": 2, "participant": "Patrycja Nowak", "path_type": "english_plus_skills", "hours": 30},
       {"recommendation_id": 3, "participant": "Piotr Nowak", "path_type": "business_english", "hours": 60}]',
     '{"testimonials": ["b2c_couple_case"]}', 'https://files.example/offers/deal2-v1.pdf', 'sent', 5),

    -- Scenario 3: v1 sketch superseded after regrouping -> v2 accepted
    (4, 3, 1, 'b2b_group', 230, 29900.00, 'PLN',
     '[{"recommendation_id": 4}, {"recommendation_id": 5}, {"recommendation_id": 6}, {"recommendation_id": 7}, {"recommendation_id": 8}]',
     '{"case_studies": ["dach_expansion"]}', 'https://files.example/offers/deal3-v1.pdf', 'superseded', 5),
    (5, 3, 2, 'b2b_group', 230, 28500.00, 'PLN',
     '[{"recommendation_id": 4}, {"recommendation_id": 5}, {"recommendation_id": 6}, {"recommendation_id": 7}, {"recommendation_id": 8}]',
     '{"case_studies": ["dach_expansion"], "note": "regrouped into 2 level-based groups, adjusted price"}',
     'https://files.example/offers/deal3-v2.pdf', 'accepted', 5),

    -- Scenario 4: offer rejected together with the lost deal
    (6, 4, 1, 'b2b_group', 100, 13000.00, 'PLN',
     '[{"recommendation_id": 9, "participant": "Robert Gajda", "hours": 50},
       {"recommendation_id": 10, "participant": "Iwona Szulc", "hours": 50}]',
     NULL, 'https://files.example/offers/deal4-v1.pdf', 'rejected', 5);

-- ----------------------------------------------------------------------------
-- Tasks (mirror of Planka cards; representative sample, not every stage)
-- ----------------------------------------------------------------------------
INSERT INTO tasks (id, deal_id, planka_card_id, stage, task_type, title, assignee_id, status, completed_at)
OVERRIDING SYSTEM VALUE VALUES
    -- Scenario 1
    (1, 1, 'plk-101', 'qualified',      'verify_lead',               'Verify lead: Jedrzej Kowalski', 1, 'done', now() - interval '23 days'),
    (2, 1, 'plk-102', 'analysis',       'paste_transcript_discovery','Paste/approve transcript: discovery Jedrzej', 1, 'done', now() - interval '20 days'),
    (3, 1, 'plk-103', 'recommendation', 'needs_analysis',            'Needs analysis + recommendation: Jedrzej', 2, 'done', now() - interval '18 days'),
    (4, 1, 'plk-104', 'adjustment',     'adjust_offer',              'Adjust offer after demo: Jedrzej (60h -> 40h)', 1, 'done', now() - interval '13 days'),
    (5, 1, 'plk-105', 'offer_sent',     'send_offer',                'Send offer v2: Jedrzej', 1, 'done', now() - interval '12 days'),
    -- Scenario 2
    (6, 2, 'plk-201', 'qualified',      'verify_lead',               'Verify lead: Patrycja Nowak', 1, 'done', now() - interval '20 days'),
    (7, 2, 'plk-202', 'analysis',       'add_participant',           'Add second participant (Piotr) mentioned in discovery', 1, 'done', now() - interval '16 days'),
    (8, 2, 'plk-203', 'recommendation', 'needs_analysis',            'Needs analysis + recommendations: Patrycja + Piotr', 2, 'done', now() - interval '15 days'),
    -- Scenario 3
    (9, 3, 'plk-301', 'analysis',       'verify_participants',       'Verify 5 AI-drafted participants from discovery', 1, 'done', now() - interval '28 days'),
    (10, 3, 'plk-302', 'audit',         'audit_results',             'Audit results: group A (3 participants)', 3, 'done', now() - interval '21 days'),
    (11, 3, 'plk-303', 'audit',         'audit_results',             'Audit results: group B (2 participants)', 3, 'done', now() - interval '20 days'),
    (12, 3, 'plk-304', 'audit',         'confirm_audits_complete',   'Confirm audits complete: Olatech', 3, 'done', now() - interval '19 days'),
    (13, 3, 'plk-305', 'adjustment',    'adjust_offer',              'Adjust offer: Olatech (regroup by level)', 1, 'done', now() - interval '11 days'),
    -- Scenario 4
    (14, 4, 'plk-401', 'audit',         'audit_results',             'Follow-up audit results: Iwona Szulc', 3, 'done', now() - interval '12 days'),
    (15, 4, 'plk-402', 'lost',          'provide_lost_reason',       'Provide lost reason: JanTrans', 1, 'done', now() - interval '5 days'),
    -- Scenario 5
    (16, 5, 'plk-501', 'disqualified',  'verify_lead',               'Verify lead: Zbigniew Spamowski (disqualified)', 1, 'done', now() - interval '9 days');

-- ----------------------------------------------------------------------------
-- Realign identity sequences after explicit-ID inserts
-- ----------------------------------------------------------------------------
SELECT setval(pg_get_serial_sequence('users', 'id'),               (SELECT max(id) FROM users));
SELECT setval(pg_get_serial_sequence('clients', 'id'),             (SELECT max(id) FROM clients));
SELECT setval(pg_get_serial_sequence('deals', 'id'),               (SELECT max(id) FROM deals));
SELECT setval(pg_get_serial_sequence('deal_status_history', 'id'), (SELECT max(id) FROM deal_status_history));
SELECT setval(pg_get_serial_sequence('participants', 'id'),        (SELECT max(id) FROM participants));
SELECT setval(pg_get_serial_sequence('meetings', 'id'),            (SELECT max(id) FROM meetings));
SELECT setval(pg_get_serial_sequence('audit_results', 'id'),       (SELECT max(id) FROM audit_results));
SELECT setval(pg_get_serial_sequence('recommendations', 'id'),     (SELECT max(id) FROM recommendations));
SELECT setval(pg_get_serial_sequence('offers', 'id'),              (SELECT max(id) FROM offers));
SELECT setval(pg_get_serial_sequence('tasks', 'id'),               (SELECT max(id) FROM tasks));

COMMIT;