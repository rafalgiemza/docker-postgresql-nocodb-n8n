# CoAction — projekt bazy NocoDB (faza 2, v3)

Zmiany vs v2: warstwa **rekomendacji** (`recommendations`, `recommendation_items`,
`training_modules`, `pricing`), historia ocen w osobnej tabeli (`assessments`
zamiast płaskich `participants.cefr_*`), rozbicie blobu `meetings.ai_analysis`
na pola strukturalne, przeniesienie ceny/godzin/przycisku generowania do
`offers`. Powód: `.ai/Opis_procesu.txt` §3–§10 wymaga, żeby każda rzecz, która
ma trafić na slajd oferty, była **osobnym polem**, a nie akapitem w markdownie.

Stack: PostgreSQL + NocoDB CE + n8n, self-hosted (2× Sfera Host VPS PRO).
Konwencja nazw — bez zmian vs v2: pola po angielsku w `snake_case`, etykiety
w UI mogą być po polsku.

---

## Zasada organizująca: brudnopis → AI → czystopis

Cały proces to trzy warstwy danych. Nie mieszaj ich w jednej tabeli:

| Warstwa | Co to | Kto pisze | Przykład |
|---|---|---|---|
| **Brudnopis** | surowe wejście, nieustrukturyzowane | człowiek / n8n | `meetings.transcript`, `meetings.notes` |
| **Draft AI** | wynik LLM, jeszcze niezatwierdzony | n8n (przycisk „generuj…") | `meetings.goals`, `assessments.needs_summary` |
| **Czystopis** | zatwierdzone dane, z których powstaje oferta | człowiek (zmiana statusu) | te same pola po `ai_accepted` |

Draft i czystopis to **te same pola** — różni je tylko status wiersza. Człowiek
nie przepisuje treści z pola do pola, tylko poprawia i zatwierdza.

### Konwencja statusu AI (jednolita w całej bazie)

Każda tabela, w której coś generuje LLM, ma **jedno** pole SingleSelect
`ai_status` (nie jedno na pole — wszystkie pola AI danej tabeli generujemy
jedną akcją i zatwierdzamy razem):

`none` → `pending` → `ai_draft_ready` → `ai_accepted` / `ai_rejected`

- `none` — nie próbowano generować (wartość domyślna)
- `pending` — n8n odpalił LLM, czekamy (guard przed podwójnym kliknięciem)
- `ai_draft_ready` — jest draft, czeka na człowieka → n8n tworzy task weryfikacji
- `ai_accepted` — **jedyny stan, z którego wolno budować ofertę**
- `ai_rejected` — odrzucone, n8n tworzy task naprawczy

`meetings.processing_status` z v2 przemianuj na `ai_status` i ujednolić wartości
— dziś ma `analysis_pending`/`ai_draft_ready`/`ai_accepted`, czyli prawie to samo
pod inną nazwą. Inaczej każdy workflow potrzebuje własnego guarda.

---

## Architektura tabel

```
companies ──< leads ──< meetings ──< assessments
    │           │  \──< participants ──< assessments
    │           │  \                \──< recommendations ──< recommendation_items >── training_modules
    │           │  \──< tasks
    │           │  \──< activities        (append-only, pisze TYLKO n8n)
    │           │  \──> testimonials      (wybrane referencje do oferty)
    │           └────< offers >── offer_templates
    └─────< participants
projects ──< tasks >── task_templates
pricing   (samodzielny cennik, bez relacji — patrz §11)
```

Trzy poziomy merytoryczne, świadomie rozdzielone:

```
assessment      = CO JEST        (audyt: CEFR, luki, potrzeby)        per uczestnik
recommendation  = CO PROPONUJEMY (typ ścieżki, uzasadnienie, moduły)  per uczestnik
offer           = ZA ILE         (cena, godziny, plik, wersja)        per lead
```

W B2B jeden lead ma N uczestników, każdy z własną oceną i własną rekomendacją,
ale **jedną wspólną ofertę**. To jest powód, dla którego rekomendacja nie może
wisieć na leadzie.

---

## 1. `leads` — zmiany

Lead to szansa sprzedaży, nie osoba ucząca się. Kanban zostaje tutaj.

**Dodaj:**

| Pole | Typ NocoDB | Wypełnia | Uwagi |
|---|---|---|---|
| `industry` | SingleSelect | człowiek / AI | dla B2C — branża klienta; dla B2B dubluje `companies.industry`, ale lead bywa wcześniej niż firma |

**Usuń / przenieś:**

| Pole | Co z nim | Dlaczego |
|---|---|---|
| `training_hours` | → `offers.hours` | godziny to atrybut konkretnej oferty, nie leada |
| przycisk „generate offer" | → `offers` | patrz §6 |
| `lead_id` (bigint) | usuń albo przemianuj na `legacy_id` | myląca nazwa — pole o nazwie `lead_id` w tabeli `leads` |

**ZOSTAW `value`.** To prognoza wartości szansy (do raportów pipeline'u,
ustawiana wcześnie, zanim istnieje oferta) — **to nie to samo co `offers.price`**,
czyli konkretna kwota na konkretnym dokumencie. Nie łącz ich.

**`offer_prep_status`** — po dodaniu `offers.status` przestaje być źródłem prawdy
o ofercie. Zostaw wyłącznie jako bramkę „czy wolno generować" (`draft_ready`),
albo usuń i bramkuj po `recommendations.ai_status = ai_accepted`.

---

## 2. `meetings` — zmiany

Blob `ai_analysis` nie nadaje się do renderu oferty — trzeba pola.

**Dodaj (wszystkie generowane jednym promptem z `transcript` + `notes`):**

| Pole | Typ NocoDB | Wypełnia | Uwagi |
|---|---|---|---|
| `goals` | LongText | AI → człowiek | cele klienta (§3) |
| `challenges` | LongText | AI → człowiek | wyzwania |
| `participant_types` | LongText | AI → człowiek | typy uczestników |
| `business_context` | LongText | AI → człowiek | kontekst biznesowy (§4 „Kontekst biznesowy") |
| `communication_situations` | LongText | AI → człowiek | sytuacje komunikacyjne — wprost zasilają audyt |
| `ai_status` | SingleSelect | n8n / człowiek | wartości wg konwencji wyżej |

**Zmień:**

| Pole | Co z nim |
|---|---|
| `ai_analysis` | przemianuj na `ai_analysis_raw` — zostaje do wglądu/debugu, nie jest źródłem dla oferty |
| `processing_status` | przemianuj na `ai_status`, ujednolić wartości |

`meetings.type` niech rozróżnia `discovery` / `audit` / `inne` — audyt uczestnika
(§5) to też spotkanie i może produkować `assessments`.

---

## 3. `participants` — zmiany

Osoba ucząca się. **W B2C tworzymy ją zawsze**, nawet gdy to ta sama osoba co
`leads.contact_name` — inaczej nie ma gdzie trzymać oceny i rekomendacji,
a generator oferty (iteruje po uczestnikach) wyrenderuje pustą ofertę.
W4 powinien tworzyć ją automatycznie dla B2C z danych kontaktowych.

**Dodaj:**

| Pole | Typ NocoDB | Wypełnia | Uwagi |
|---|---|---|---|
| `role_context` | LongText | człowiek / AI | z kim i o czym rozmawia, odbiorcy komunikacji — „kontekst biznesowy" dla B2C, gdzie nie ma `companies` |
| `frequency` | SingleSelect | człowiek | jak często używa angielskiego: `codziennie`/`kilka_razy_w_tyg`/`rzadko` |
| `self_assessment` | LongText | człowiek / formularz | samoocena z formularza przed-audytowego (§5) |
| `manager_needs` | LongText | człowiek | potrzeby wg managera/HR (§5) |

**Usuń (leftover po v2):**

`cefr_overall`, `cefr_range`, `cefr_accuracy`, `cefr_fluency`,
`cefr_communication` — źródłem prawdy jest `assessments`. Zostawienie ich
gwarantuje, że ktoś kiedyś wpisze dane w złe miejsce.

**`needs_summary`** — zdecyduj jeden dom. Rekomendacja: zostaje na
`assessments` (bo zmienia się z każdym audytem), a z `participants` usuń.
**`audit_notes`** — przenieś na `assessments` jako `auditor_notes`.

---

## 4. `assessments` (dziś `Assesments`)

Historia ocen: jeden wiersz na audyt. Najnowsza ocena = `sort=-UpdatedAt`,
bez osobnej flagi „aktualna".

> **Uwaga migracyjna:** tabela już istnieje pod nazwą `Assesments` (literówka),
> ID `my2chrbzjb4425x`, z danymi i podpięta w W9. **Zmień tytuł w UI NocoDB,
> nie twórz nowej** — ID tabeli przy zmianie tytułu zostaje, więc W9 działa
> dalej bez zmian. Sprawdź po zmianie, czy NocoDB przemianował też fizyczną
> tabelę w Postgresie (`crm."Assesments"`), czy tylko etykietę.

| Pole | Typ NocoDB | Wypełnia | Uwagi |
|---|---|---|---|
| `title` | SingleLineText (display value) | człowiek | np. „audyt wstępny", „po 3 miesiącach" |
| `assessed_at` | Date | człowiek | data audytu |
| `cefr_overall` | SingleLineText | człowiek | poziom ogólny, np. `B2.4` |
| `cefr_range` | SingleLineText | człowiek | zakres |
| `cefr_accuracy` | SingleLineText | człowiek | poprawność |
| `cefr_fluency` | SingleLineText | człowiek | płynność |
| `cefr_communication` | SingleLineText | człowiek | komunikatywność |
| `strengths` | LongText | człowiek / AI | mocne strony (§5) |
| `gaps` | LongText | człowiek / AI | luki (§5) |
| `needs_summary` | LongText | AI → człowiek | podsumowanie potrzeb — **to leci na slajd oferty** |
| `auditor_notes` | LongText | człowiek | obserwacje audytora (przeniesione z `participants.audit_notes`) |
| `ai_status` | SingleSelect | n8n / człowiek | wg konwencji |
| `participant` | Links → participants | — | wymagane |
| `meeting` | Links → meetings | — | opcjonalne (audyt bywa nienagrywany) |

**Usuń `Level`** — dubluje `cefr_overall`.

---

## 5. `recommendations` — NOWA

Co proponujemy tej konkretnej osobie. Oddzielone od audytu, bo to inna decyzja,
innego człowieka i w innym momencie (§7).

| Pole | Typ NocoDB | Wypełnia | Uwagi |
|---|---|---|---|
| `title` | SingleLineText (display value) | człowiek | |
| `type` | SingleSelect | człowiek / AI | `business_english` / `english_plus_skills` / `skills_only` / `mieszana` |
| `rationale` | LongText | AI → człowiek | uzasadnienie — **leci na slajd oferty** |
| `priority` | SingleSelect | człowiek | `wysoki` / `sredni` / `niski` |
| `headline` | SingleLineText | AI → człowiek | jednozdaniowa rekomendacja na slajd |
| `ai_status` | SingleSelect | n8n / człowiek | wg konwencji |
| `participant` | Links → participants | — | wymagane |
| `items` | Links → recommendation_items | auto | |

---

## 6. `recommendation_items` — NOWA

Konkretna ścieżka: które moduły, w jakiej kolejności, ile godzin, w jakim trybie.
Zastępuje proponowane wcześniej `offer_module_selection` (tamto wisiało na
**leadzie**, przez co w B2B wszystkie ścieżki wpadały do jednego worka).

| Pole | Typ NocoDB | Wypełnia | Uwagi |
|---|---|---|---|
| `sort_order` | Number | człowiek | kolejność etapów (ETAP 1, ETAP 2…) |
| `hours` | Number | człowiek | godziny dla tego modułu |
| `mode` | SingleSelect | człowiek | `1-1` / `w_parach` / `grupa` |
| `recommendation` | Links → recommendations | — | wymagane |
| `training_module` | Links → training_modules | — | wymagane |

To zasila slajd `repeat:module` w szablonie PPTX — zamiast dzisiejszych
zaszytych na sztywno slajdów „ETAP 1 / ETAP 2".

---

## 7. `training_modules` — NOWA

Biblioteka modułów szkoleniowych (dziś istnieją tylko jako tekst na slajdach).

| Pole | Typ NocoDB | Wypełnia | Uwagi |
|---|---|---|---|
| `title` | SingleLineText (display value) | człowiek | np. „Business English" |
| `category` | SingleSelect | człowiek | `business_english` / `english_for_it` / `workshop_facylitacja` / `workshop_negocjacje` / `inne` |
| `goal_statement` | LongText | człowiek | cel modułu — na slajd |
| `description` | LongText | człowiek | opis — na slajd |
| `default_hours` | Number | człowiek | domyślna liczba godzin (podpowiedź) |
| `active` | Checkbox | człowiek | nieaktywne nie pojawiają się w wyborze |

---

## 8. `offers` — zmiany

Jedna oferta = jeden wygenerowany dokument. Wiele ofert na lead (wersje, warianty).

**Dodaj:**

| Pole | Typ NocoDB | Wypełnia | Uwagi |
|---|---|---|---|
| `hours` | Number | człowiek | łączna liczba godzin (przeniesione z `leads.training_hours`) |
| `variant` | SingleSelect | człowiek | `standard` / `intensive_workshop` / `oferta_specjalna` |
| `version` | Number | n8n | kolejny numer wersji dla tego leada — pod „historię ofert" (§10) |
| `sent_at` | Date | n8n | ustawiane przy wysyłce |
| `valid_until` | Date | człowiek | termin ważności oferty |
| przycisk `generate offer` | Button → webhook W9 | — | **przeniesiony z `leads`** |
| `ai_status` | — | — | **nie dodawaj** — oferta nie jest generowana przez LLM, tylko z szablonu |

**Usuń:** `Text` (śmieciowa kolumna).

**Zostaw bez zmian:** `title`, `status` (`draft`/`sent`/`accepted`/`rejected`),
`price`, `template_name`, `file`, `data_json`, `warnings`, Links → `leads`.

> `data_json` zostaje snapshotem danych użytych do renderu — to jest realizacja
> wymogu „możliwość powrotu do historii ofert" (§10). Nawet jeśli lead się
> zmieni, wiadomo dokładnie, co wysłano.

**Konsekwencja dla W9:** przycisk na `offers` oznacza, że workflow dostaje
w payloadzie wiersz oferty, nie leada — trzeba przejść po Linku do leada
i dalej po uczestnikach. Dziś jest odwrotnie. To zmiana w `Assemble render data`.

---

## 9. `testimonials` — zmiany

**Dodaj:** `position` (SingleLineText) — stanowisko osoby wystawiającej
referencję; szablon PPTX już go używa (`{{testimonial.position}}`).

---

## 10. `companies` — zmiany

**Dodaj:**

| Pole | Typ NocoDB | Wypełnia | Uwagi |
|---|---|---|---|
| `communication_processes` | LongText | AI → człowiek | procesy komunikacyjne, kluczowe role, odbiorcy (§4) |
| `business_impact` | LongText | AI → człowiek | wpływ biznesowy braków językowych |

Dla B2C te informacje mieszkają na `participants.role_context` — patrz §3.

---

## 11. `pricing` — NOWA (samodzielna)

Cennik wersjonowany. **Świadomie bez relacji** do ofert — to tabela
referencyjna, z której człowiek odczytuje stawkę i wpisuje `offers.price`.

| Pole | Typ NocoDB | Wypełnia | Uwagi |
|---|---|---|---|
| `segment` | SingleSelect | człowiek | **te same wartości co `offers.variant`** |
| `mode` | SingleSelect | człowiek | **te same wartości co `recommendation_items.mode`** |
| `hours` | Number | człowiek | próg godzinowy |
| `price` | Currency (PLN) | człowiek | cena za ten pakiet |
| `valid_from` | Date | człowiek | |
| `valid_to` | Date | człowiek | puste = obowiązuje |

> **Do rozstrzygnięcia:** czy `offers.price` ma być przepisywane ręcznie
> z cennika, czy liczone przez n8n (`hours` × stawka)? Dopóki to nie jest
> ustalone, `pricing` jest tylko ściągą dla człowieka. Zadbaj, żeby
> `pricing.segment` i `offers.variant` miały **identyczną listę wartości** —
> inaczej automatyczne dopasowanie nigdy nie będzie możliwe.

---

## 12. `document_templates` (dziś `offer_templates`) — zrób od razu

Serwis renderujący jest **generyczny** (szablon + dane → plik, zero wiedzy
o ofertach), więc obsłuży też inne dokumenty. Najbliższy kandydat jest wprost
w procesie: **raport audytowy** (§6 — „draft raportu na podstawie danych
z audytu i szablonu raportu"). Ten sam mechanizm, inny szablon i inne `data`.

Skoro nie ma jeszcze produkcji ani danych — uogólnij teraz:

| Zmiana | Na co |
|---|---|
| tytuł tabeli | `offer_templates` → `document_templates` |
| nowe pole `kind` | SingleSelect: `offer` / `audit_report` / `inne` |
| filtr w W9 | `(active,eq,true)` → `(active,eq,true)~and(kind,eq,offer)` |

**Ale `offers` zostaje `offers` — nie łącz go w `documents`.** To nie jest
argument o koszcie migracji (dziś zerowym), tylko o modelu: oferta ma cenę,
termin ważności i cykl `draft`→`sent`→`accepted`/`rejected` wobec klienta.
Raport audytowy nie ma żadnej z tych rzeczy. Jedna tabela na oba typy to połowa
kolumn pusta w każdym wierszu i statusy, które dla połowy rekordów nic nie
znaczą. **Wspólny jest szablon i renderer, nie rekord wynikowy.**

Raport audytowy nie potrzebuje własnej tabeli — jest artefaktem audytu, więc
niech mieszka na `assessments`:

| Pole | Typ NocoDB | Wypełnia | Uwagi |
|---|---|---|---|
| `report_file` | Attachment | n8n | wyrenderowany raport (ten sam serwis, szablon `kind=audit_report`) |
| `report_data_json` | LongText | n8n | snapshot danych użytych do raportu |

---

## Relacje do utworzenia

| Z tabeli | Pole | Typ | Do tabeli |
|---|---|---|---|
| `participants` | `assessments` | has-many | `assessments` |
| `meetings` | `assessments` | has-many | `assessments` |
| `participants` | `recommendations` | has-many | `recommendations` |
| `recommendations` | `items` | has-many | `recommendation_items` |
| `training_modules` | `recommendation_items` | has-many | `recommendation_items` |

Relacje `leads`↔`offers`, `leads`↔`participants`, `leads`↔`testimonials`,
`participants`↔`meetings` — już istnieją, bez zmian.

---

## Kolejność wdrożenia w NocoDB

Rób w tej kolejności — późniejsze kroki zależą od wcześniejszych:

1. **Zrzuć aktualny schemat** (`make dump-appdata-schema`) — obecny
   `appdata/appdata_schema.sql` jest nieaktualny (brakuje `Assesments.needs_summary`,
   `Leads.training_hours`, `Testimonials.position`).
2. Przemianuj `Assesments` → `assessments`, usuń `Level`, dodaj brakujące pola (§4).
3. Utwórz `training_modules` (§7) — niezależna, nic od niej nie zależy.
4. Utwórz `recommendations` (§5) + relację do `participants`.
5. Utwórz `recommendation_items` (§6) + relacje do `recommendations` i `training_modules`.
6. Utwórz `pricing` (§11).
7. Dodaj pola strukturalne na `meetings` (§2), przemianuj `ai_analysis` i `processing_status`.
8. Dodaj pola na `participants` (§3), potem **dopiero** usuń `cefr_*` — najpierw
   sprawdź, czy nic ich nie czyta (W9 już nie czyta).
9. Dodaj pola na `offers` (§8), przenieś przycisk z `leads`.
10. Drobiazgi: `testimonials.position`, `companies.*`, `leads.industry`.

**Po każdym kroku dotykającym pól używanych przez workflowy** — przebieg
Test Runnera na VPS-B przed powtórzeniem na produkcji.

---

## Co się zmienia w W9 i szablonie oferty

Po tej migracji generator dostanie dane, których dziś nie ma:

| Nowe w `data` | Źródło | Placeholder w PPTX |
|---|---|---|
| `participant.recommendation.type` | `recommendations.type` | `{{participant.recommendation.type}}` |
| `participant.recommendation.rationale` | `recommendations.rationale` | `{{participant.recommendation.rationale}}` |
| `participant.recommendation.headline` | `recommendations.headline` | `{{participant.recommendation.headline}}` |
| `module[]` | `recommendation_items` + `training_modules` | slajd z notatką `repeat:module`, w środku `{{module.title}}`, `{{module.hours}}`, `{{module.mode}}`, `{{module.goal_statement}}` |
| `offer.hours`, `offer.variant` | `offers` | bez zmian w szablonie |
| `meeting.goals`, `meeting.challenges` | `meetings` | `{{meeting.goals}}` itd. |

Kontrakt szablonu (markery `repeat:`, forma z prefiksem i bez) —
patrz `file-renderer-service/README.md`. Serwis renderujący **nie wymaga żadnych zmian**
— zweryfikowane testami na docelowym kształcie danych
(`file-renderer-service/test_schema_v3_contract.py`).

> **Jedno wiązanie dla n8n: moduły trzeba spłaszczyć.** Renderer nie obsługuje
> zagnieżdżonego repeat (slajdy są płaskie), więc `participant[].module[]`
> NIE zadziała. `data.module[]` musi być listą płaską — jeden wiersz na parę
> (uczestnik, moduł) — z nazwą osoby przepisaną do elementu jako
> `module.participant_name`. Na slajdzie `repeat:module` odwołanie
> `{{participant.full_name}}` celuje w globalną *listę* uczestników, nie
> w osobę.
