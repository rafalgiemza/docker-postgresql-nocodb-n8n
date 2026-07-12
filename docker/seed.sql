-- ============================================================================
-- CoAction CRM — dane referencyjne (seed)
-- Usage:  wgrywane przez docker/app_seed.sh
--         (psql --username appdata_owner --dbname appdata < ./seed.sql)
--
-- Uruchamiane PO docker/schema.sql. Bezpiecznie re-runnable dla sekcji
-- users/pricing_tiers (ON CONFLICT DO NOTHING na naturalnych kluczach) —
-- testimonials nie ma naturalnego klucza, więc czyścimy ją jawnie przed insertem.
--
-- Źródło prawdy: .ai/IMPLEMENTATION_PLAN.md §3 ("Dane referencyjne do zasiania"),
-- .ai/PRD.md §2.5/§2.7. Zespół (users) potwierdzony w rozmowie z klientem
-- (2026-07-12): CEO strony coaction.pl → sekcja zespołu operacyjnego.
-- ============================================================================

-- ============================================================================
-- 1. Users
-- ============================================================================
-- Tylko role zgodne z appdata.users.role CHECK ('sales','auditor','methodologist','admin','bot').
-- Paulina Jaranowska (opiekunka finansowa) i Katarzyna Rybak (Growth Manager)
-- świadomie pominięte — ich role nie są jeszcze zamodelowane w schemacie
-- (brak 'finance'/'marketing' w CHECK), patrz IMPLEMENTATION_PLAN.md §7.

INSERT INTO appdata.users (full_name, email, role) VALUES
    ('Przemysław Fidzina', 'p.fidzina@coaction.pl',  'sales'),
    ('Dorota Michalska',   'd.michalska@coaction.pl', 'auditor'),
    ('Aleksandra Kubiak',  'a.kubiak@coaction.pl',    'auditor')
ON CONFLICT (email) DO NOTHING;

-- Uwaga dla WF-3 (Faza 5, audyt scheduling — PRD linia 641): przypisanie
-- auditor_user_id NIE jest losowe — Dorota obsługuje audyty B2B (klienci
-- firmowi), Aleksandra ("Ola") obsługuje audyty B2C (klienci indywidualni).
-- Reguła wiąże się z clients.type, nie ma osobnej kolumny "specialization" —
-- workflow ma odczytać opportunities.client_id → clients.type i wybrać
-- auditora na tej podstawie.

-- ============================================================================
-- 2. Pricing tiers — PLACEHOLDER, do podmiany na realny cennik (slajd 8)
-- ============================================================================
-- TODO(Faza 6 / import Excela): podmienić na rzeczywiste stawki i daty
-- obowiązywania z decku ofertowego. Struktura (product/hours/format/price)
-- jest zgodna ze schematem — trigger cenowy na offer_items działa niezależnie
-- od tego, czy wartości są docelowe czy placeholder.

INSERT INTO appdata.pricing_tiers (product, hours, format, price_pln, valid_from) VALUES
    ('Business English 1:1',  15, '1-1',   4500.00, '2026-01-01'),
    ('Business English 1:1',  30, '1-1',   8800.00, '2026-01-01'),
    ('Business English 1:1',  45, '1-1',  12900.00, '2026-01-01'),
    ('Business English 1:1',  60, '1-1',  16800.00, '2026-01-01'),
    ('Warsztat grupowy',      15, 'group', 3600.00, '2026-01-01')
ON CONFLICT ON CONSTRAINT uq_pricing_tiers_natural_key DO NOTHING;

-- ============================================================================
-- 3. Testimonials — PLACEHOLDER, do podmiany na katalog ze slajdów 12–24
-- ============================================================================
-- TODO(Faza 6 / import Excela): podmienić na realne cytaty klientów i
-- poprawne slide_template_idx (mapowanie na numery slajdów w szablonie 1638).
-- Brak naturalnego klucza w tabeli — czyścimy przed insertem, żeby seed
-- pozostał re-runnable bez duplikatów.

DELETE FROM appdata.testimonials WHERE slide_template_idx BETWEEN 12 AND 24;

INSERT INTO appdata.testimonials (author, role, quote, tags, slide_template_idx) VALUES
    ('Placeholder Klient A', 'Head of People, Firma X',        'Placeholder — realny cytat do uzupełnienia.', ARRAY['IT', 'B2B'], 12),
    ('Placeholder Klient B', 'Area Sales Manager, Firma Y',     'Placeholder — realny cytat do uzupełnienia.', ARRAY['sales', 'B2B'], 13),
    ('Placeholder Klient C', 'Ekspert HR, klient indywidualny', 'Placeholder — realny cytat do uzupełnienia.', ARRAY['HR', 'B2C'], 14)
;
