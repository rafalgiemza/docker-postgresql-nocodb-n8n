# Generowanie ofert w schemacie v4: porównanie i plan zmian

Status: **propozycja do akceptacji** (2026-10-28). Dotyczy etapu 4 planu
migracji (`nocodb_crm_migration_v4.md`). Nic w W1 ani w `init-schema.py` nie jest
jeszcze zmienione; powstał tylko test kontraktu
(`file-renderer-service/test_schema_v4_contract.py`).

Porównałem cztery rzeczy:

1. **kontrakt v3** z `file-renderer-service/test_schema_v3_contract.py`
   (docelowy kształt `data` z sierpnia),
2. **W1 dziś** (`W1_generate_offer.json`, węzeł „Assemble offer data”),
3. **prawdziwy szablon** `init-data/source/ofer-template-1.0.pptx`
   (28 slajdów, poza gitem),
4. **bazę v4** (`schema_map.json` ze świeżego dumpu) oraz żywą bazę v3 sprzed
   migracji (`schema_map.json` z commitu `608ed48`).

## 1. Co szablon naprawdę chce

Renderer z pustym `data` zgłasza dokładnie 19 brakujących wartości. To jest
rzeczywisty kontrakt szablonu v1.0 (przypięty testem):

| Placeholder | Slajdy | W1 dziś wysyła? | Źródło w v4 |
|---|---|---|---|
| `lead.contact_name` | 1 | tak (`leads.lead_name`) | imię i nazwisko **kupującego**: `sale_opportunities.person` |
| `assessment.position`, `assessment.needs_summary` | 1, 3 | tak (pierwszy uczestnik) | najnowsza ocena osoby z rekomendacji: `persons.assessments` (stanowisko: ocena, a gdy brak `persons.position`) |
| `a.o`, `a.r`, `a.a`, `a.f`, `a.c` | CEFR | tak | `assessments.cefr_*` tej samej oceny |
| `offer.date`, `offer.hours`, `offer.price` | 1, 4 | tak | dzisiejsza data, `offers.hours`, `offers.total_price` (rollup) |
| `package.hours` | 5, 6, … | **nie**, wysyła listę `packages` | `selected_package_variants_cores.hours`; szablon czyta OBIEKT `package`, nie listę |
| `BusinessEnglish15h.price`, `BusinessEnglish15hinpair.price`, `skills1on1.price`, `skillsgroup.price` | tabela cen | **nie** | `pricing` (`offers.pricing`); W1 nigdy nie czytał cennika |
| `testimonial.content/.name/.position` | 16, 24, 25 | **nie** | `offers.selected_testimonials` (`content`, `client_name`, `position`) |

Skutek na prawdziwym szablonie, dla kształtu danych z W1 dziś: **27 slajdów
zamiast 28 i 15 ostrzeżeń** (slajd z referencjami wypada, brak `package.hours`,
brak cen). To nie jest skutek migracji do v4; W1 nigdy nie wysyłał tych danych.
Szablon dogonił W1 albo odwrotnie.

## 2. Co zniknęło lub zmieniło się w bazie v4

Pola, których W1 używa albo musi używać, i ich los:

| W1 / kontrakt używa | Stan w bazie v4 | Co robimy |
|---|---|---|
| `offers.leads` (`rows[0].leads.Id`) | zastąpione `offers.sale_opportunity` | W1 czyta szansę, a z niej kupującego i firmę |
| `participants` (`full_name`, `position`, `assessments`) | tabela usunięta | osoby z `recommendations.person`, oceny z `persons.assessments` |
| `recommendations.participants` | zastąpione `recommendations.person` | j.w. |
| `offers.cover_style` (→ `data.key`), `offers.logo_wall_style` | **brak**: ktoś dodał je ręcznie w UI starej bazy, a `init-schema.py` ich nie zna | dopisać do `init-schema.py` (§4, O1) |
| `offers.generation status` | **brak**: j.w. | zastąpi `completion_status` (nowy skill §3) albo dopisać stare pole |
| `recommendations.selected_others`, `selected_package_variants_others` | w v4 powstały `…_adons`; README mówi, że poprawna nazwa to `…_others` | ujednolicić (§4, O1) |
| `module[]` (kontrakt v3: `recommendation_items` + `training_modules`) | tabel nie ma; zastąpił je model pakietów (`selected_package_variants_cores/others`, `recommendation_packages`) | usunąć z kontraktu, W1 już ich nie używa |
| `lead.type` (B2B/B2C) | `leads.lead_type` został, ale logika jest na szansie | `sale_opportunities.segment` (opcjonalnie) |
| `meeting.*`, `company.*` (kontrakt v3) | istnieją (`meetings`, `companies`) | szablon v1.0 ich nie używa; dodać do `data`, gdy szablon będzie chciał |

W v3 pola `package_core_slides.internal_name` i `…_others` także różniły się od
`init-schema.py` (żywa baza miała nazwy z UI). Wzorzec jest ten sam: **żywa
baza v3 zawierała ręczne zmiany, których skrypt nie znał**, więc świeża baza z
`init-schema.py` ich nie ma.

## 3. Problemy znalezione przy okazji (niezależne od schematu)

1. **Szablon, slajd 25/26 (`repeat:testimonials`)**: placeholdery to
   `{{testimonial.x}}` (liczba pojedyncza), a znacznik powtórzenia to
   `testimonials`. Prefiks pojedynczy czyta osobny, globalny obiekt, więc **obie
   kopie slajdu pokażą tę samą referencję**. Poprawka w szablonie:
   `{{testimonials.x}}`. Slajd 24 ma dodatkowo literówkę `{{testimonial.name}`
   (brakuje nawiasu). Pinuje to test z `xfail(strict)`.
2. **`data.recomendation`** w W1 ma literówkę; szablon v1.0 jej nie używa, więc
   można poprawić na `recommendation` razem z W1.
3. **Treść AI bez bramki.** Zasada z `.ai/rules/ai-n8n.md` §8 (render używa tylko
   zaakceptowanego tekstu) nie jest zaimplementowana w W1: `needs_summary` i
   uzasadnienie rekomendacji idą do dokumentu bez sprawdzenia `ai_status`.
4. **Szablon jest wersją roboczą**: notatki na slajdach 4–6 („będą to ograniczone
   warianty”, „ilość slajdów zależy od ilości celi”) mówią, że powtarzanie
   pakietów (`repeat:`) jeszcze nie jest zrobione. Dziś `package.hours` czyta
   jeden obiekt.

## 4. Plan zmian

Kolejność i rozmiar (S małe, M średnie, L duże):

| # | Zmiana | Rozmiar | Zależy od |
|---|---|---|---|
| O0 | Decyzje z §5 | | |
| O1 | **Schemat** (`init-schema.py` + `make init-schema STAGE=4`): `offers.cover_style` (SingleSelect boy/girl/man/woman, według README renderera), `offers.logo_wall_style` (opcje do podania), `offers.completion_status` wg decyzji D3; ujednolicenie nazw `others`/`adons`; (opcjonalnie) `pricing.key` z D5. `add_missing_fields` dopisze pola do istniejącej tabeli `offers` | S/M | D1–D3, D5 |
| O2 | **Kontrakt renderera**: `test_schema_v4_contract.py` (**zrobione**, 89 testów zielonych, 1 oczekiwany `xfail`). Po zmianach szablonu zaktualizować `EXPECTED_PLACEHOLDERS` | S | |
| O3 | **Szablon** (autor szablonu): `{{testimonials.x}}` na slajdzie 25, nawias na 24, decyzja o `repeat:` dla pakietów (D4) | S | D4 |
| O4 | **W1 v4**: przepisany pod nowe zasady (placeholdery ID, alias Set, `completion_status`, `linkrow`). Szczegóły w §6 | L | O1, D2, D3, D6 |
| O5 | Pozostałe flow ofertowe na v4: W10 (uzasadnienie rekomendacji), W9 (teksty pakietów), W6b (pipeline oferty), plus nowe z etapu 4: przejście na `approved` (zapis `approved_total`, `deal_value`) i „Utwórz nową wersję” (kopia rekomendacji) | L | O4 |
| O6 | **Seed i odbiór**: seed etapu 4 uzupełniony o `cover_style`, `logo_wall_style`, wybrane referencje i cennik; uruchomić W1 na ofercie z seeda i porównać `data_json` z `DATA_V4` z testu | M | O4, O5 |

## 5. Decyzje do podjęcia

| # | Pytanie | Rekomendacja |
|---|---|---|
| D1 | Jakie wartości ma `offers.logo_wall_style`? Nigdzie w repo ich nie znalazłem (README renderera podaje tylko `cover_style`: boy/girl/man/woman) | podaj listę; do tego czasu pole z jedną opcją-placeholderem |
| D2 | Nazwy `…_others` czy `…_adons`? README (sekcja „Rozjazd skrypt ↔ żywa baza”) mówi, że poprawne jest `others`, a skrypt tworzy `adons` | przejść na `others`; tabele etapu 4 są świeże, więc najtaniej usunąć je i utworzyć ponownie (`make init-schema STAGE=4`) |
| D3 | Status W1: `completion_status` (nowy skill §3, wartości none / collecting data / creating file / generating / done / error) na `offers`? Obecnie `offers` ma `status` (cykl oferty), `version_status` (przycisk nowej wersji) i nie ma `generation status` | dodać `completion_status` do `offers` i używać go w W1; `status` zostaje jako cykl życia oferty (draft…accepted) |
| D4 | Pakiety w szablonie: jeden obiekt `package` (dziś) czy `repeat:package` dla slajdów 5–6 (lista celów/pakietów)? | `repeat:package` z listą; to decyzja autora szablonu |
| D5 | Ceny: jak z wierszy `pricing` zrobić klucze `BusinessEnglish15h`, `skills1on1`…? Deterministycznie, bez parsowania tytułów, potrzebne pole-klucz | dodać `pricing.key` (tekst = nazwa placeholdera); W1 buduje `data[key] = {price}` z wierszy `offers.pricing` |
| D6 | Kto jest adresatem oferty (`lead.contact_name`)? | kupujący, czyli `sale_opportunities.person` (B2B: główny kontakt, np. Marek); dla B2C to ta sama osoba co uczestnik |
| D7 | Konwencja flow: nowy skill (`.claude/skills/n8n-flow`) zastąpił „Get one base” placeholderami (`make fill-workflows`), dodał `completion_status` i Set-aliasy, a **moje wygenerowane flow (W0, W2, W3, W6a, W7, W14–W21) i generator nadal używają starej konwencji** | przed O4 przerobić generator na placeholdery (`__TBL_*__`, `__COL_*__`); `completion_status` i aliasy osobno, bo wymagają zmian w schemacie wielu tabel |

## 6. Projekt W1 v4 (O4)

Wejście: przycisk „generuj ofertę” na `offers` (webhook `w1-generate-offer-v12`,
payload zbadany w `docs/n8n-nocodb-operations.md` §5).

1. **Set „Offer from button”**: alias `offer` = `rows[0]` (Id, `hours`,
   `total_price`, `cover_style`, `logo_wall_style`, relacje jako `{Id, …}`).
2. **Update row**: `completion_status` = `collecting data` (tylko to pole).
3. **Walidacje** (IF): jest szablon (`document_templates`), jest szansa
   (`sale_opportunity`), są rekomendacje (`recommendations` nie puste), jest
   pakiet. Każda odmowa: `completion_status` = `error` + komunikat w
   `warnings`, bez zadania (polityka błędów v4).
4. **Równoległe odczyty** (`linkrow`, tylko potrzebne pola) i jeden Merge:
   - szansa i jej kupujący, firma (`sale_opportunity` → `person`, `company`);
   - rekomendacje oferty (`type`, `headline`, `rationale`, `priority`,
     `ai_status`) i dla każdej: osoba, wybrane pakiety (`selected_cores`,
     `selected_others`: `hours`, `price`, link do pakietu i slajdów);
   - najnowsza ocena każdej osoby (`persons.assessments`);
   - referencje (`offers.selected_testimonials`);
   - cennik (`offers.pricing`);
   - szablon (`document_templates`, plik).
5. **„Assemble offer data”** (jedyna granica przed renderem), kształt:

   | Klucz | Wartość |
   |---|---|
   | `key` | `offers.cover_style` |
   | `lead.contact_name` | imię i nazwisko kupującego |
   | `company` | `{name, communication_processes, business_impact}` (dla B2B) |
   | `offer` | `{date, hours, price}` |
   | `assessment`, `a` | najnowsza ocena pierwszej osoby (CEFR; `needs_summary` **tylko** gdy `ai_status` = `ai_accepted`, inaczej puste) |
   | `participant[]` | osoby oferty: `full_name`, `position`, `a{}`, `assessment{}`, `recommendation{}` (tekst AI tylko gdy zaakceptowany) |
   | `package` (obiekt) albo `package[]` | wg D4: pierwszy pakiet / lista, z `hours`, `name`, `description` |
   | `adons[]` albo `others[]` | wybrane dodatki: `key`, `name`, `description`, `hours` |
   | `<Wariant>` | z `pricing`: `{price}` po `pricing.key` (D5) |
   | `testimonial`, `testimonials[]` | wybrane referencje: `content`, `name` (= `client_name`), `position`; **oba klucze** (pojedynczy do slajdów stałych, lista do `repeat:`) |
   | `logo_wall[]` | `[{key: offers.logo_wall_style}]` |

6. `completion_status` = `creating file` → render
   (`file-renderer-service`) → upload do NocoDB → **Update offer** (`file`,
   `data_json` ze zrzutem `data`, `warnings` z nagłówka `X-Warnings`) →
   `completion_status` = `done`. Gałąź błędu: `error` + komunikat + wpis w
   `activities`.
7. **Bez zadania „review offer”** po wygenerowaniu (usunięte w Dodatku A planu
   migracji); weryfikację oferty obsługuje stan `status` = `draft` → `approved`.

## 7. Co zrobiłem teraz, a czego nie

- Dodałem `file-renderer-service/test_schema_v4_contract.py`: przypina kształt
  `data` z §6, prawdziwe 19 placeholderów szablonu v1.0, lukę „W1 dziś” oraz
  błąd powtarzania referencji w szablonie. Cały zestaw renderera: 89 testów
  zielonych, 1 oczekiwany `xfail`. Testy z prawdziwym szablonem pomijają się,
  gdy pliku `init-data/source/ofer-template-1.0.pptx` nie ma.
- Nie ruszyłem `init-schema.py`, W1 ani szablonu: czekają na decyzje z §5.

## 8. Decyzje usera (2026-10-29) i lista pól bazy dla W1 v13

Decyzje: (1) `logo_wall_style` = `b2b` / `it`; (2) nazwy `others` (nie `adons`);
(3) status generowania wg skilla `n8n-flow` §3; (4) `repeat:packages` - jedna
oferta dla wielu osób, wysyłana do płacącego leada, który nie musi być
uczestnikiem; (5) ceny w następnej iteracji (nowy szablon z cenami) - W1 v13 ich
nie wysyła; (6) lead = oferta → szansa → `source_lead.lead_name` (fallback:
kupujący); (7) flow wg nowych zasad (placeholdery + `make fill-workflows`).

**Odstępstwo od nazwy z decyzji 3:** pole nazywa się `offers.completion_status`
(nie `generation_status`), bo skill §3 każe używać wszędzie jednej nazwy
`completion_status` (tak samo `assessments`). Wartości: `none`, `collecting data`,
`creating file`, `generating`, `done`, `error`.

| Tabela | Pole | Typ | Status | Do czego |
|---|---|---|---|---|
| `offers` | `cover_style` | SingleSelect boy/girl/man/woman | **nowe** | `data.key` (okładka) |
| `offers` | `logo_wall_style` | SingleSelect `b2b`/`it` | **nowe** | `data.logo_wall[0].key` |
| `offers` | `completion_status` | SingleSelect (6 wartości) | **nowe** | postęp generowania; błąd w `warnings` |
| `offers` | `document_templates`, `recommendations`, `selected_testimonials`, `sale_opportunity`, `hours`, `total_price`, `title`, `file`, `data_json`, `warnings` | - | istnieją | jak w v12 |
| `recommendations` | `person`, `headline`, `rationale`, `ai_status`, `title`, `selected_cores`, `selected_others` | - | istnieją (`selected_adons` → `selected_others`) | uczestnicy, tekst rekomendacji (tylko `ai_accepted`) |
| `selected_package_variants_cores` | `title`, `hours`, `slides` | - | istnieją | `packages[].name/hours` |
| `package_core_slides` | `name`, `title`, `description` | - | istnieją | `packages[].title/description` |
| `selected_package_variants_others` (było `…_adons`) | `hours`, link `package_variants_others` | - | **rename** | `others[].hours` |
| `package_variants_others` (było `…_adons`) | `key`, `name`, `description` | - | **rename** | `others[]` |
| `persons` | `full_name`, `position`, `assessments` | - | istnieją | `participants[]` |
| `assessments` | `needs_summary`, `ai_status`, `position`, `cefr_*` | - | istnieją | `assessment`, `a` |
| `testimonials` | `content`, `client_name`, `position` | - | istnieją | `testimonial(s)` |
| `leads` | `lead_name` | - | istnieje | `lead.contact_name` |

Rename wymaga na żywej bazie jednego z dwóch kroków (tabele etapu 4 są świeże):
zmienić nazwy w UI NocoDB (tabele, pola `selected_adons`→`selected_others`,
`adons_subtotal`→`others_subtotal`, formułę) albo usunąć `…_adons` i uruchomić
`make init-schema STAGE=4`; potem `make dump-crm-schema`.

Flow: `W1v13_generate_offer.json` (webhook `w1-generate-offer-v13`). Kontrakt
danych przypina `file-renderer-service/test_schema_v4_contract.py`. Znane luki
szablonu v1.0: `{{package.hours}}` (potrzebny `repeat:packages`), ceny wariantów,
slajdy 24/25 (testimonials).
