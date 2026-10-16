# Propozycja schematu CRM v4: lead ≠ szansa sprzedaży, osoby w jednej tabeli

Status: **propozycja do akceptacji**, nic nie jest jeszcze zmienione w
`scripts/init-schema.py` ani we flow. Punkt wyjścia: schemat v3
(`docs/archive/fable/nocodb_crm_schema_v3.md`, `scripts/init-schema.py`).
Inspiracja strukturalna: model Pipedrive (Persons / Organizations / Leads /
Deals / Activities), z którego klient korzystał wcześniej.

## 1. Po co ta zmiana

W v3 jedna tabela `leads` jest jednocześnie zgłoszeniem (źródło, kwalifikacja
MQL/SQL) i szansą sprzedaży (etap, wartość, utrata). Dla klienta to dwa różne
byty: lead to ktoś, kto się zgłosił, szansa sprzedaży powstaje dopiero z
zakwalifikowanego leada. Dodatkowo dane osób są rozsiane po `leads`
(`lead_name`, `contact_email`, `contact_phone`) i `participants`
(`full_name`, `email`).

Zasady nowego modelu:

1. **Jedna tabela osób (`persons`).** Dane osobowe (imię, e-mail, telefon) są
   tylko tam. Tabela `participants` z v3 znika.
2. **Rola wynika z powiązania, nie ze statusu osoby.** Ta sama osoba może być
   kupującym w jednej szansie, uczestnikiem w innej i gościem spotkania:

   | Rola | Jak zapisana | Od kiedy |
   |---|---|---|
   | Kupujący | `sale_opportunities.person` | utworzenie szansy |
   | Attendee | link `meetings` ↔ `persons` | zaplanowanie spotkania (discovery, audyt, demo) |
   | Participant | link `sale_opportunities` ↔ `persons` (bez własnej tabeli i statusów) | **dopiero po podpisaniu umowy** |
3. **Lead = wejście do lejka, szansa = to, co sprzedajemy.** Szansa należy do
   osoby i firmy, nie do leada. Lead jest tylko źródłem atrybucji
   (`source_lead`) i jest puste dla kontynuacji, upsellów i powrotów.
4. **Historia etapów jest osobną tabelą**, żeby dało się liczyć prędkość
   lejka.
5. **NocoDB-first zostaje.** Tabele tworzy `init-schema.py` przez API NocoDB,
   bez migracji SQL, triggerów i widoków `v_*` z PRD Pipedrive-clone.

## 2. Diagram relacji (zmiany względem v3)

```
companies ──< persons                        persons.company (0..1)
companies ──< leads                          (bez zmian)
companies ──< sale_opportunities             NOWE

persons ──< leads                            leads.person (wymagane)
persons ──< sale_opportunities               sale_opportunities.person (wymagane, główny kontakt)
persons >──< meetings                        NOWE ("attendees")
persons >──< sale_opportunities              NOWE ("participants", ustawiane po podpisaniu umowy)
persons ──< assessments                      assessments.person (było: przez participants)
persons ──< recommendations                  recommendations.person (było: przez participants)

leads ──< sale_opportunities                 sale_opportunities.source_lead (0..1, unikalne)

sale_opportunities ──< sale_opportunity_stage_history   NOWE
sale_opportunities ──< offers                (było leads ──< offers)
sale_opportunities ──< meetings              (było leads ──< meetings)
sale_opportunities ──< tasks, activities     (leads ──< tasks/activities zostaje, bo lead
                                              ma własne zadania, np. "zakwalifikuj")
```

Usunięte z v3: tabela `participants` wraz z relacjami `companies →
participants`, `leads → participants`, `participants → assessments`,
`participants → recommendations`, `participants ↔ meetings`.

Bez zmian: `offers → recommendations / pricing / selected_testimonials`, cała
gałąź pakietów i rekomendacji, `testimonials`, `materials`,
`document_templates`, `projects`, `task_templates`, `newsletter_stats`.

## 3. Tabele

Typy w konwencji `init-schema.py`. „(link)" oznacza relację NocoDB (Links).

### 3.1 `persons` (NOWA)

Każdy człowiek, jeden wiersz na osobę. Dedup po e-mailu.

| Pole | Typ | Uwagi |
|---|---|---|
| `full_name` | SingleLineText | tytuł wiersza |
| `email` | Email | klucz dedupu (W4 szuka po nim) |
| `phone` | PhoneNumber | |
| `position` | SingleLineText | było `participants.position` |
| `linkedin_url` | URL | było `participants.linkedin_url` |
| `company` | link → `companies` | 0..1, zmiana pracy = przepięcie linku |
| `industry` | SingleSelect (INDUSTRY) | dla B2C bez firmy; było `leads.industry` |
| `role_context` | LongText | było `participants.role_context`; kontekst biznesowy, dla B2C bez `companies` |
| `frequency` | SingleSelect codziennie/kilka_razy_w_tyg/rzadko | było `participants.frequency` |
| `assigned_methodologist` | User | było `participants.assigned_methodologist` |
| `notes` | LongText | |
| `possible_duplicate` | link M2M → `persons` | przeniesione z `leads` |
| `legacy_id` | Number | jeśli import będzie łączył osoby |

### 3.2 `leads` (ODCHUDZONA)

Zgłoszenie i jego kwalifikacja. Bez etapów sprzedaży i wartości.

| Pole | Typ | Uwagi |
|---|---|---|
| `lead_name` | SingleLineText | tytuł; np. „Jan Kowalski – Acme" (wypełnia n8n) |
| `person` | link → `persons` | **nowe**, wymagane |
| `company` | link → `companies` | bez zmian (intake i `company_match_status`) |
| `received_at` | DateTime | **nowe**; „Data wpłynięcia" z Excela, dla importu |
| `lead_type` | SingleSelect B2C/B2B | bez zmian |
| `lead_source` | SingleSelect | bez zmian |
| `contact_channel` | SingleSelect | bez zmian |
| `owner` | User | bez zmian |
| `qualification` | SingleSelect | bez zmian (`unqualified`, `non-MQL`, `MQL`, `non-SQL`, `SQL`) |
| `disqualify_reason`, `disqualify_note` | SingleSelect, LongText | bez zmian |
| `company_match_status` | SingleSelect | bez zmian (W4v2/W5) |
| `possible_duplicate` | — | **usunięte**, przechodzi na `persons` |
| `notes`, `legacy_id` | LongText, Number | bez zmian |

Przechodzą do `sale_opportunities`: `stage`, `state`, `loss_reason`,
`loss_note`, `deal_value`, `label`, `offer_prep_status`, `training_goals`,
`offer_sent_at`, `contract_sent_at`, `closed_at`.
Znikają z `leads`: `contact_email`, `contact_phone` (są w `persons`),
`industry` (jest w `persons`/`companies`).

### 3.3 `sale_opportunities` (NOWA)

Szansa sprzedaży = to, co jest dziś kanbanem po `stage` w `leads`.

| Pole | Typ | Uwagi |
|---|---|---|
| `name` | SingleLineText | tytuł; np. „Acme – kurs grupowy" |
| `person` | link → `persons` | **wymagane**, kupujący B2C albo główny kontakt B2B |
| `company` | link → `companies` | 0..1, dla B2B |
| `source_lead` | link → `leads` | 0..1, unikalne; tylko dla szansy powstałej z leada |
| `segment` | SingleSelect B2C/B2B | było `leads.lead_type` |
| `owner` | User | |
| `stage` | SingleSelect | patrz pytanie otwarte 1 |
| `state` | SingleSelect open/won/lost/archived | bez zmian |
| `label` | SingleSelect | „typ szansy" z Excela (Nowy klient, Upsell, Odnowienie…); patrz pytanie 4 |
| `deal_value` | Currency PLN | prognoza (≠ `offers.total_price`), nazwa i opis bez zmian |
| `loss_reason`, `loss_note` | SingleSelect, LongText | |
| `offer_prep_status`, `training_goals` | SingleSelect, LongText | używane przez W1/W6b |
| `offer_sent_at`, `contract_sent_at`, `closed_at` | Date | pisze n8n, bez zmian |
| `service_end_date` | Date | **opcjonalne**, pod widok odnowień; patrz pytanie 5 |
| `participants` | link M2M → `persons` | osoby szkolone; wypełniane przy podpisaniu umowy (sekcja 3.5) |
| `notes`, `legacy_id` | LongText, Number | |

Relacje wychodzące: `meetings`, `tasks`, `activities`, `offers`,
`sale_opportunity_stage_history`.

### 3.4 `sale_opportunity_stage_history` (NOWA)

Jeden wiersz na każdą zmianę etapu. Pisze wyłącznie n8n (W2) oraz import.

| Pole | Typ | Uwagi |
|---|---|---|
| `sale_opportunity` | link → `sale_opportunities` | |
| `from_stage` | SingleSelect | puste dla pierwszego wpisu |
| `to_stage` | SingleSelect | te same opcje co `stage` |
| `changed_at` | DateTime | dla importu: oryginalna data z Excela |
| `changed_by` | SingleLineText | `n8n:W2`, `import`, albo użytkownik |

### 3.5 Participants: link, nie tabela

Tabela `participants` z v3 jest usuwana. „Participant" to osoba, która po
podpisaniu umowy będzie się uczyć, i jest zapisana jako zwykły link M2M
`sale_opportunities.participants` ↔ `persons`. Link wypełnia się **przy
podpisaniu umowy** (dla B2C: kupujący jest swoim własnym participantem).

Skutki:

- Przed umową wszyscy ludzie są attendees spotkań (discovery, audyt, demo).
  Dla B2B z 15 audytowanymi i 10 zapisanymi: 15 osób to attendees audytów
  z ocenami, a 10 trafia do linku participants.
- „Nie zapisani" to attendees audytu, których nie ma w participants. Osobny
  status nie jest potrzebny.
- Zniknęły statusy `candidate`, `audit_scheduled`, `audited`, `enrolled`,
  `not_enrolled`. Koszt: nie da się śledzić kandydata, który nie ma jeszcze
  zaplanowanego spotkania. Zastępują to zadania („umów audyt z X") podpięte do
  osoby.
- Pola, które były na `participants`, mają nowy dom:

| Stare pole `participants.*` | Nowe miejsce |
|---|---|
| `full_name`, `email`, `position`, `linkedin_url` | `persons` |
| `role_context`, `frequency`, `assigned_methodologist` | `persons` |
| `self_assessment`, `manager_needs` | `assessments` (zbierane przy audycie) |

### 3.6 Pozostałe tabele (zmiany relacji)

- `meetings`: `leads → meetings` zamienione na `sale_opportunities → meetings`
  (0..1, bo spotkanie może być przed powstaniem szansy). Nowa relacja M2M
  `meetings ↔ persons` („attendees"), dzięki niej widać wszystkie spotkania
  osoby. M2M `participants ↔ meetings` znika razem z tabelą.
- `assessments`: `participants → assessments` zamienione na `persons →
  assessments`. Zostaje relacja `meetings → assessments`. Pola `self_assessment`
  i `manager_needs` dopisane (LongText, z `participants`). Ocena należy do
  osoby, więc historia jej poziomu jest dostępna między szansami.
- `recommendations`: `participants → recommendations` zamienione na `persons →
  recommendations`. Zostaje `offers → recommendations`.
- `tasks`, `activities`: dodana relacja do `sale_opportunities`, relacja do
  `leads` zostaje (zadanie „zakwalifikuj leada" nie ma jeszcze szansy).
- `offers`: `leads → offers` zamienione na `sale_opportunities → offers`.
- `companies`: dodane relacje do `persons` i `sale_opportunities`; usunięta do
  `participants`. Opis tabeli („lead to pojedyncza szansa") do poprawki na
  „szansa sprzedaży".

## 4. Mapowanie starych pól `leads`

| Stare `leads.*` | Nowe miejsce |
|---|---|
| `lead_name` | `leads.lead_name` oraz `sale_opportunities.name` |
| `contact_email`, `contact_phone` | `persons.email`, `persons.phone` |
| `lead_type` | `leads.lead_type` i `sale_opportunities.segment` |
| `owner`, `lead_source`, `contact_channel` | `leads.*` (a `owner` także na szansie) |
| `qualification`, `disqualify_*` | `leads.*` |
| `company_match_status` | `leads.company_match_status` |
| `possible_duplicate` | `persons.possible_duplicate` |
| `industry` | `persons.industry` (B2C) / `companies.industry` (B2B) |
| `stage`, `state` | `sale_opportunities.*` |
| `loss_reason`, `loss_note` | `sale_opportunities.*` |
| `deal_value`, `label` | `sale_opportunities.*` |
| `offer_prep_status`, `training_goals` | `sale_opportunities.*` |
| `offer_sent_at`, `contract_sent_at`, `closed_at` | `sale_opportunities.*` |
| `notes`, `legacy_id` | `leads.*` i `sale_opportunities.*` |

Import z Excela (jeden wiersz): `persons` (0..1 kontakt) + `companies`
(0..1) + `leads` + `sale_opportunities` (0..1, tylko gdy jest „Data szansy
sprzedaży" lub data dowolnego etapu) + wiersze `sale_opportunity_stage_history`
po jednym na każdą niepustą datę etapu. Szczegóły kolumn: sekcja 11.3 w
`.ai/pipedrive-clone-prd.md`.

## 5. Nowe zachowanie: konwersja lead → szansa

Dziś lead sam jest szansą. Teraz ktoś (lub coś) musi ją utworzyć, gdy lead
przejdzie kwalifikację do `SQL`. Reguły, żeby flow było bezpieczne przy
ponownym uruchomieniu:

- sprawdź, czy istnieje szansa z tym `source_lead`; jeśli tak, nic nie rób,
- utwórz `sale_opportunities` z `person`, `company`, `segment`, `owner`,
  `source_lead`, etapem początkowym i `name`,
- zapisz pierwszy wiersz w `sale_opportunity_stage_history`,
- utwórz zadanie „umów badanie potrzeb".

Rekomendacja: **Button „Utwórz szansę sprzedaży" na leadzie** (jak w
Pipedrive „Convert to deal"), a nie automat na zmianę pola, zgodnie z
istniejącym wzorcem Buttonów w repo i brakiem ryzyka pętli webhooków.

## 6. Wpływ na flow (liczba odwołań do `leads` w JSON; `participants` podane osobno)

| Flow | Odwołań | Co się zmienia |
|---|---|---|
| W1 generate_offer | 14 | (+11 odwołań do `participants`) czyta z `sale_opportunities`, kupujący z `person`, osoby oferty z `recommendations.person` |
| W4v2 intake_matching | 9 | dopasowuje/tworzy `person`, potem tworzy `lead` (nie szansę) |
| W4v3 cf7_intake | 6 | jw.; dziś tworzy też `participants` (5 odwołań), po zmianie osoba trafia tylko do `persons` |
| W8 assessment_needs_summary | 3 | 10 odwołań do `participants`; nowa ścieżka `assessments.person` + `meetings`, szansa przez spotkanie |
| W2 stage_change | 2 | działa na `sale_opportunities`, dopisuje historię etapów |
| W5 company_dedup | 2 | do sprawdzenia; ewentualnie dedup `persons` |
| W6b offer_pipeline | 2 | `sale_opportunities` |
| W13 lead_inquiry_analysis | 2 | do sprawdzenia, czy wynik ląduje na leadzie czy szansie |
| W7 bookings_meetings_sync | 1 | (+1 odwołanie do `participants`) łączy spotkanie z `person` (attendees), szansą jeśli jedna otwarta |
| W9 offer_package_texts | 1 | `sale_opportunities` |
| NOWY | | konwersja lead → szansa (sekcja 5) |
| W0, W3, W4, W6a, W10, W11 | 0 | bez zmian w treści; do weryfikacji po odświeżeniu ID |

Po zmianie schematu: `make dump-crm-schema` i przegląd hardkodowanych ID w
każdym flow (zgodnie z `.ai/rules/nocodb.md` §1).

## 7. Migracja

CRM nie jest jeszcze na produkcji (UAT na danych testowych), więc
najtańsza jest **przebudowa od zera**, nie transformacja istniejącej tabeli:
`init-schema.py` tylko tworzy i niczego nie zmienia, więc nie przerobi
istniejącego `leads` w miejscu.

Kroki:

1. Zmiana `TABLES` i `RELATIONS` w `scripts/init-schema.py`.
2. Odtworzenie bazy testowej (staging) przez `make init-schema`.
3. Aktualizacja generatora danych testowych (`init-data/generate_crm_data.py`,
   `docs/archive/fable/seed_nocodb.py`) i importera
   (`docs/archive/fable/import_legacy_excel.py`).
4. `make dump-crm-schema`, przepięcie flow (sekcja 6), aktualizacja
   `test_cases.md`.

## 8. Poza zakresem tej zmiany (świadomie)

Migracje SQL, triggery, widoki `v_*` i rola `crm_readonly`, `consents` i
retencja RODO, `referrals`, `company_contacts` (historia zatrudnienia),
`opportunity_products`, `opportunity_contacts` (dodatkowe osoby po stronie
kupującego), automatyczne wyliczanie typu szansy. Wszystko to da się dodać
później bez przebudowy tego modelu.

## 9. Pytania otwarte (do decyzji przed implementacją)

1. **Lista etapów.** Dziś `stage`: `new`, `discovery_scheduled`,
   `discovery_done`, `audit`, `recommendation`, `offer_sent`,
   `offer_discussed`, `contract_sent`, `contract_signed`, `lost`, `archived`.
   Etapy z Excela klienta: Nowa → Badanie potrzeb → DEMO → Oferta wysłana →
   Omówienie oferty → Umowa wysłana → Umowa podpisana → Utracona. Zostawiamy
   obecne i mapujemy je przy imporcie, czy przechodzimy na etapy klienta?
2. **Stage vs state.** `state` jest wyprowadzalny z `stage`. Zostawiamy oba
   (mniej zmian we flow) czy upraszczamy?
3. **Konwersja.** Button (rekomendacja) czy automat po `qualification = SQL`?
4. **Typ szansy.** Czy `label` z Excela („Nowy klient", „Upsell",
   „Odnowienie"…) wystarcza, wpisywany ręcznie, czy chcemy później liczyć go
   regułą z historii klienta?
5. **`service_end_date`.** Dodać już teraz (pod widok „odnowienia w
   najbliższych 30 dniach"), czy dopiero gdy będzie potrzebne?

### Decyzje już podjęte

- Participant to osoba po podpisaniu umowy, zapisana jako link na szansie
  (sekcja 3.5). Przed umową wszyscy są attendees.
- Oceny i rekomendacje należą do `persons`, nie do tabeli pośredniej.
- Pola osoby szkolonej: `role_context`, `frequency`,
  `assigned_methodologist` w `persons`; `self_assessment`, `manager_needs` w
  `assessments`.

## 10. Przykład: scenariusz B2C

Anna Nowak, osoba prywatna, od formularza do podpisania umowy. Etapy wg
obecnej listy `stage` (etap `demo` dojdzie, jeśli pytanie 1 rozstrzygniemy na
etapy klienta). „Pisze" wskazuje, kto zapisuje dane: człowiek czy n8n.

### Krok 1. Formularz (n8n, W4v3)

| Tabela | Wpis |
|---|---|
| `persons` | szukaj po e-mailu; jeśli brak: `full_name`, `email`, `phone` |
| `leads` | `person` = Anna, `lead_name`, `lead_type` = B2C, `lead_source`, `contact_channel` = Formularz, `received_at`, `qualification` = unqualified, `owner` |
| `activities` | wpis o zgłoszeniu (`summary`, `payload` z formularza), podpięty do leada |
| `tasks` | „Zakwalifikuj leada: Anna Nowak", podpięte do leada |

### Krok 2. Kwalifikacja i utworzenie szansy (handlowiec, potem n8n)

| Tabela | Wpis |
|---|---|
| `leads` | `qualification` = MQL, potem SQL (albo `disqualify_reason`) |
| `sale_opportunities` | po przycisku „Utwórz szansę sprzedaży": `name`, `person` = Anna, `source_lead`, `segment` = B2C, `owner`, `stage` = new, `state` = open, `label` = Nowy klient, `deal_value` (szacunek) |
| `sale_opportunity_stage_history` | pierwszy wiersz: `to_stage` = new, `changed_by` = n8n |
| `tasks` | „Umów discovery call", podpięte do szansy |

Przycisk najpierw sprawdza, czy szansa z tym `source_lead` już istnieje.

### Krok 3. Discovery call (Bookings → W7, handlowiec, AI → W6a)

Przed spotkaniem:

| Tabela | Wpis |
|---|---|
| `meetings` | `meeting_type` = discovery, `starts_at`, `ends_at`, `status` = scheduled, `owner`, link do szansy |
| `meetings` ↔ `persons` | Anna jako attendee |
| `sale_opportunities` | `stage` = discovery_scheduled (+ wiersz historii) |

Po spotkaniu:

| Tabela | Wpis |
|---|---|
| `meetings` | `status` = done, `notes`, `transcript`; przycisk „Generuj analizę" wypełnia `goals`, `challenges`, `business_context`, `communication_situations` (`ai_status`: ai_draft_ready → ai_accepted po weryfikacji) |
| `persons` | `position`, `industry`, `role_context`, `frequency` |
| `sale_opportunities` | `training_goals`, aktualizacja `deal_value`, `stage` = discovery_done (+ wiersz historii) |
| `tasks` | „Umów audyt"; poprzednie zadanie → done |

### Krok 4. Audit call (metodyczka, AI → W8)

| Tabela | Wpis |
|---|---|
| `meetings` | `meeting_type` = audit, `starts_at`, `status` = scheduled, `owner` = metodyczka, link do szansy; po spotkaniu `status` = done, `notes`, `transcript` |
| `meetings` ↔ `persons` | Anna jako attendee |
| `sale_opportunities` | `stage` = audit (+ wiersz historii) |
| `assessments` | `person` = Anna, link do spotkania audytowego, `assessed_at`, `cefr_*`, `strengths`, `gaps`, `auditor_notes`, `self_assessment`, `manager_needs` |
| `assessments` (AI) | przycisk „Generuj needs summary": `needs_summary`, `ai_status` ai_draft_ready → ai_accepted po weryfikacji |
| `persons` | `assigned_methodologist`, jeśli już wiadomo |
| `tasks` | „Przygotuj rekomendację" dla metodyczki/handlowca |

### Krok 5. Demo, czyli prezentacja propozycji przed formalną ofertą

| Tabela | Wpis |
|---|---|
| `recommendations` | `person` = Anna, pakiety (`recommendation_packages`, `selected_package_variants_*`), teksty przez cykl AI → człowiek |
| `offers` | link do szansy, `product_type`, `pricing`, `total_price`, `hours`, `version`, `status` = draft |
| `sale_opportunities` | `offer_prep_status` → draft_ready, `stage` = recommendation (+ wiersz historii) |
| `meetings` + `persons` | spotkanie `meeting_type` = demo, Anna jako attendee |

### Krok 6. Oferta wysłana i akceptacja

| Tabela | Wpis |
|---|---|
| `offers` | po W1: `file`, `generation status` = done, `warnings`; po wysłaniu `status` = sent, `sent_at`, `valid_until`; po akceptacji `status` = accepted |
| `sale_opportunities` | `offer_sent_at`, `stage` = offer_sent (+ wiersz historii); po rozmowie o ofercie `stage` = offer_discussed |
| `meetings` + `persons` | opcjonalnie `meeting_type` = offer_discussion |
| `tasks` | „Wyślij umowę Annie" |

### Krok 7. Umowa wysłana i podpisana

| Tabela | Wpis |
|---|---|
| `sale_opportunities` | wysłanie: `stage` = contract_sent, `contract_sent_at`; podpisanie: `stage` = contract_signed, `state` = won, `closed_at`, opcjonalnie `service_end_date`; **`participants` += Anna** |
| `sale_opportunity_stage_history` | wiersze → contract_sent, → contract_signed |
| `tasks` | zadania po sprzedaży z `task_templates` (fakturowanie, przekazanie metodyczce) |
| `activities` | wpis „umowa podpisana" |

Przy porażce: `state` = lost, `stage` = lost, `loss_reason`, `loss_note`,
`closed_at`. W2 tworzy zadanie, jeśli powód jest pusty.
