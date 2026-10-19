# CoAction — projekt bazy NocoDB (v4)

Data: 2026-10-18. Status: koncepcja zaakceptowana przez klientkę na demo
(tabele `demo_*`, `scripts/demo-schema-init.py`); ten dokument jest
specyfikacją **docelowego** schematu i podstawą planu migracji. Nic w
`scripts/init-schema.py` ani we flow nie jest jeszcze zmienione.
Uzasadnienie i historia decyzji: `docs/crm-schema-v4-proposal.md`.

Zmiany vs v3:

1. **Lead ≠ szansa sprzedaży.** `leads` zostaje wejściem do lejka
   (zgłoszenie, źródło, kwalifikacja), a etapy, wartość, utrata i oferty
   przechodzą do nowej `sale_opportunities`. Tak jak w Pipedrive, z którego
   klientka korzystała wcześniej.
2. **Jedna tabela osób: `persons`.** Dane osobowe (imię, e-mail, telefon) są
   tylko tam. Tabela `participants` znika.
3. **Rola wynika z powiązania, nie ze statusu osoby.**
4. **Historia etapów** w osobnej tabeli.
5. **Zespół CoAction** (`employees`) i **nieobecności z zastępstwami**
   (`absences`) zamiast pól `User`.
6. **Zadania z datą zaplanowania** (`scheduled_for`, status `scheduled`),
   **czas w etapie** (`stage_changed_at`) i **wersje ofert** z zamrożoną sumą,
   żeby codzienna praca handlowca była na poziomie Pipedrive.

Stack i konwencje nazw bez zmian vs v3: PostgreSQL + NocoDB CE + n8n,
pola po angielsku w `snake_case`, etykiety w UI mogą być po polsku.
Zasada „brudnopis → AI → czystopis" i konwencja `ai_status` z v3 obowiązują
bez zmian (`meetings`, `assessments`, `recommendations`, `materials`).

---

## Przyjęte założenia (do potwierdzenia przed implementacją)

Demo nie rozstrzygnęło wszystkiego. Poniżej wartości, które przyjąłem, żeby
dało się planować; każda jest tania do zmiany, dopóki nie ruszy implementacja.

| # | Założenie | Dlaczego |
|---|---|---|
| A1 | Etapy `stage` mają **polskie nazwy opcji** (zespół widzi je na kanbanie); w specyfikacji używam stałych kluczy technicznych z dzisiejszego `leads.stage`, a mapowanie jest w sekcji „Nazwy etapów" niżej. Lista etapów jak dziś; do potwierdzenia, czy klientka chce zamiast niej etapy z Excela | Demo pokazywało etapy po polsku z Excela, a flow (W2 i inne) porównują wartości opcji, więc zmiana nazw to zmiana w flow |
| A2 | Pola `stage` **i** `state` zostają oba | mniej zmian we flow |
| A3 | Konwersja lead → szansa **przyciskiem** „Utwórz szansę sprzedaży" na leadzie, nie automatem po `qualification = SQL` | wzorzec Buttonów w repo, brak ryzyka pętli webhooków |
| A4 | Pole `label` zastąpione przez **`campaign`** (SingleSelect zarządzany przez zespół, np. „Black Week”). Typ szansy ma osobne pole **`opportunity_type`** (A15) | decyzja użytkownika |
| A15 | `opportunity_type` (Nowy klient / Kontynuacja / Upsell / Powrót po przerwie) jest wyliczany **raz, przy tworzeniu szansy**, przez flow W20 (bez AI), i potem się nie zmienia. Historia = wygrane szanse osoby i firmy; koniec usługi = `service_end_date`, a gdy brak: `closed_at`. Brak wygranej: Nowy klient; usługa trwa: Upsell; koniec nie dawniej niż **6 miesięcy** temu: Kontynuacja; inaczej: Powrót po przerwie | próg 6 miesięcy ustalony przez użytkownika; stała `OPPORTUNITY_TYPE_GAP_MONTHS` w generatorze |
| A5 | `service_end_date` dodane od razu | tanie, potrzebne do widoku odnowień |
| A6 | `owner` / `assignee` / `assigned_methodologist` to **linki do `employees`** (zamiast `User`); widoki „moje zadania" robimy po jednym na osobę | patrz „Ryzyka" niżej |
| A7 | Zadania powstają **tylko w trzech przypadkach** (sekcja „Zasady tworzenia zadań"); przyciski generujące wynik zadania nie tworzą | decyzja z 2026-10-18: wynik w ≤10 s, stany pośrednie widać w polu status |
| A8 | Przejścia etapów, które tworzą zadania, i ich adresaci (tabela w tej sekcji) | propozycja do potwierdzenia |
| A10 | `to_be_audited` / `audited` / `participants` mają semantykę **przeniesienia**: osoba czeka w `to_be_audited`, po utworzeniu oceny n8n przenosi ją do `audited`, a przy podpisaniu umowy wybrani trafiają do `participants` | każde pole odpowiada na jedno pytanie, a liczby widać od razu na karcie szansy; alternatywa: zostawić osobę w `to_be_audited` (łatwiejsze, ale gorzej widać, kto jeszcze czeka) |
| A11 | Rezerwacje przez **cal.com w chmurze** (zastępuje MS Bookings). Audyt umawia się na dwa sposoby: klient rezerwuje przez link metodyczki, albo metodyczka rezerwuje w cal.com w imieniu klienta (podaje jego e-mail). Oba tworzą rezerwację z webhookiem; wydarzenie wpisane bezpośrednio w kalendarzu, poza cal.com, nie jest widoczne dla n8n i wymaga ręcznego wpisu spotkania. Typ spotkania to wyłącznie pole `meeting_type` (SingleSelect), ustawiane z **typu wydarzenia cal.com** (`eventTypeId`) przez stałe mapowanie w flow; flow nigdy nie wnioskuje typu z tytułu | zastępuje A11 z MS Bookings; wymaga osobnych typów wydarzeń cal.com dla discovery, audytu i demo (PRD Q8) oraz webhooków przy każdym z nich; widok „Spotkania bez typu" łapie typy spoza mapowania |
| A9 | `audit_scope` jest jednym polem na szansie (zakres audytu dla całej firmy), indywidualne uwagi trafiają do `assessments.auditor_notes` | wystarcza dla B2B i B2C; do przeniesienia, jeśli zakres ma być per osoba |
| A12 | Notatki: **bez osobnej tabeli**. Pola `notes` (LongText) na leadzie, szansie i osobie to miejsce na notatki, które mają przetrwać; `activities` zostaje logiem pisanym wyłącznie przez n8n. Akcja z terminem („odezwać się za 3 dni") to zadanie | decyzja użytkownika; brak osi czasu rozmów (świadomy koszt) |
| A13 | Follow-up = **zadanie** z `scheduled_for` i statusem `scheduled`, tworzone przez handlowca. Na szansie jest tylko `stage_changed_at` (pisze W2) i widok „Utknięte"; **nie ma** `follow_up_date` | szansa wisząca w etapie bez żadnej reakcji jest widoczna w „Utknięte", a zaplanowane kontakty w widokach zadań |
| A14 | Wersje ofert: w momencie `approved` n8n zapisuje `offers.approved_total` (zamrożona suma) i aktualizuje `sale_opportunities.deal_value`; nowa wersja powstaje przyciskiem „Utwórz nową wersję", który kopiuje rekomendacje razem z `selected_package_variants_*` | `total_price` jest rollupem, więc przeniesienie rekomendacji zmieniłoby sumę starej wersji; alternatywa: przenosić rekomendacje i polegać na `data_json` jako historii (prostsze, ale suma starej wersji znika) |

---

## Zasady organizujące

**Kto jest kim wynika z powiązań:**

| Rola | Jak zapisana | Od kiedy |
|---|---|---|
| Osoba w leadzie (zaangażowana w decyzję) | `leads.persons` (M2M) | zgłoszenie; może nigdy nie zostać attendee ani participantem |
| Kupujący / główny kontakt | `sale_opportunities.person` | utworzenie szansy |
| Attendee | `meetings.attendees` (M2M) | zaplanowanie spotkania |
| Do audytu | `sale_opportunities.to_be_audited` (M2M) | dodanie osoby do listy audytowej (ręcznie; dla B2C automatycznie kupujący) |
| Po audycie | `sale_opportunities.audited` (M2M) | utworzenie oceny (n8n przenosi osobę z `to_be_audited`) |
| Participant (osoba szkolona) | `sale_opportunities.participants` (M2M) | **dopiero po podpisaniu umowy** |

- Postęp audytów widać na karcie szansy w trzech polach: `to_be_audited`
  (czeka), `audited` (po audycie), `participants` (zapisani na szkolenie).
  „Nie zapisany" = osoba w `audited`, której nie ma w `participants`. Osobny
  status nie istnieje.
- Lead to osoba **lub grupa osób** i może przynieść **wiele szans** (np. dwa
  działy jednej firmy naraz albo kolejne zakupy po latach). Szansa ma
  najwyżej jeden `source_lead`; kolejne szanse znanego klienta mogą wskazywać
  ten sam lead i wtedy dziedziczą osoby z procesu decyzyjnego i źródło.
- `participants` to **pole relacji w `sale_opportunities`**, nie tabela.
- Pracownicy CoAction to `employees`; klienci i kontakty to `persons`.

**Tytuł jest dla zespołu, nie dla n8n.** Pole tytułowe rekordu (`name`,
`title`, `full_name`, `lead_name` itd.) służy ludziom: pojawia się w linkach i
listach, żeby było widać, o jaki wpis chodzi, zanim się go otworzy. Zespół
może nazywać wpisy dowolnie i zmieniać nazwy w każdej chwili. **Dla n8n
deterministyczne są tylko pola SingleSelect** (oraz linki i klucze takie jak
`email`, `external_id`). Konsekwencje:

- żaden flow nie czyta tytułu, żeby zdecydować, co zrobić (typ spotkania
  rozpoznaje po `meeting_type`, rodzaj zadania po `task_type`, etap po
  `stage`, segment po `segment`); n8n tytuły tylko **zapisuje**;
- każde rozróżnienie, na którym opiera się automatyzacja, musi mieć własne
  pole SingleSelect; jeśli go brakuje, dodajemy pole, a nie parsujemy tekst;
- sprawdzenie „czy to już istnieje" (idempotencja) robimy po linkach i
  SingleSelectach, nie po treści tytułu.

**Trzy poziomy merytoryczne** (zmiana vs v3 tylko w tym, do czego się wiążą):

```
assessment      = CO JEST        (audyt: CEFR, luki, potrzeby)   per OSOBA
recommendation  = CO PROPONUJEMY (ścieżka, uzasadnienie, moduły) per OSOBA
offer           = ZA ILE         (cena, godziny, plik, wersja)   per SZANSĘ
```

---

## Zasady tworzenia zadań

Przyciski generujące (analiza spotkania, `needs_summary`, oferta, slajdy)
zwracają wynik w ok. 10 s, a stany pośrednie widać w polu `status`
(SingleSelect, `.ai/rules/common.md` §2). **Zadanie po kliknięciu przycisku
nie powstaje**, bo użytkownik widzi wynik zaraz po odświeżeniu.

Zadanie tworzymy tylko wtedy, gdy człowiek musi coś zrobić, a rekord sam tego
nie pokaże:

1. **Potencjalny klient wypełnił formularz.** „Zakwalifikuj leada: <nazwa>"
   dla `leads.owner` (z regułą zastępstwa), link do `lead`.
2. **Szansa przechodzi na etap wymagający uwagi innego członka zespołu.**
   Adresaci według tabeli niżej (A8).
3. **Nikt nie zatwierdził szkicu AI od wczoraj.** Dzienny flow szuka rekordów
   z `ai_status` = `ai_draft_ready`, ostatnio zmienianych ponad 24 h temu
   (`meetings`, `assessments`, `recommendations`; w `materials` pola
   `content_ai_status` i `outline_ai_status`). Jedno zadanie na rekord, link do
   rekordu; pomija rekord, który ma już otwarte zadanie z `task_type` =
   `approve_ai_draft` i linkiem do tego rekordu. Adresat: osoba
   odpowiedzialna za zatwierdzenie (`meetings.owner`; dla ocen
   `persons.assigned_methodologist` lub `owner` spotkania audytowego; dla
   rekomendacji `owner` szansy) z regułą zastępstwa.

Przejścia etapów tworzące zadania (propozycja, A8):

| Przejście | Zadanie | Dla | Linki w zadaniu |
|---|---|---|---|
| → `audit` | „Przygotowanie audytu: <osoba> (<firma>)" **po jednym na osobę z `to_be_audited`** | metodyczka wg `segment` (B2B / B2C) lub `persons.assigned_methodologist`, jeśli ustawiona | `sale_opportunity`, `person`, `meeting` (discovery call z transkrypcją i analizą AI). Zakres audytu wpisuje do `sale_opportunities.audit_scope` |
| → `recommendation` | „Przygotuj ofertę: <szansa>" | `owner` szansy | `sale_opportunity` |
| → `contract_signed` | „Wystaw fakturę: <szansa>" oraz „Przejmij uczestników: <szansa>" | finanse; metodyczka z `persons.assigned_methodologist` | `sale_opportunity` |

W B2C przy przejściu na `audit` n8n dopisuje kupującego do `to_be_audited` i
tworzy zadanie sam. W B2B handlowiec uzupełnia `to_be_audited` i klika przycisk
**„Generuj zadania audytowe"** na szansie (sekcja 3). Przycisk jest tu wyjątkiem
od zasady „przycisk nie tworzy zadania": jego jedynym celem jest utworzenie
zadań, a nie wynik do obejrzenia.

Rodzaj zadania zapisuje flow w polu `tasks.task_type` (SingleSelect):
`qualify_lead` (przypadek 1), `audit_prep`, `prepare_offer`, `invoice`,
`take_over_participants` (przypadek 2), `approve_ai_draft` (przypadek 3),
`provide_input` (wąski przypadek 4: brakuje danych wejściowych, np. transkrypcji,
bez których flow nie ruszy; jedno otwarte zadanie na rekord),
`other` (zadania ręczne i cykliczne). Tytuł zadania („Przygotowanie audytu:
<osoba> (<firma>)" itp.) jest tylko opisem dla zespołu.

Etapy bez zadania: `new`, `discovery_scheduled`, `discovery_done`, `offer_sent`,
`offer_discussed`, `contract_sent`, `lost`, `archived` (ten sam handlowiec albo
nic do zrobienia). Kontakt po tych etapach („odezwać się za 3 dni") handlowiec
zapisuje sam jako zadanie z `scheduled_for` i statusem `scheduled`.

Nie dotyczy: zadania cykliczne z `task_templates` (W0) i zadania tworzone
ręcznie w UI.

---

## Architektura tabel

```
companies ──< persons
companies ──< leads
companies ──< sale_opportunities
companies ──< testimonials

persons >──< leads                       leads.persons (osoba lub grupa)
persons ──< sale_opportunities           kupujący
persons >──< sale_opportunities          participants, audited
persons >──< meetings                    attendees
persons ──< assessments, recommendations, tasks

leads ──< sale_opportunities             source_lead (lead: wiele szans; szansa: 0..1 lead)
leads ──< tasks, activities

sale_opportunities ──< sale_opportunity_stage_history
sale_opportunities ──< meetings, offers, tasks, activities

meetings ──< assessments, activities
meetings, assessments, recommendations, offers ──< tasks      (rekord do przygotowania / zatwierdzenia)
offers >── recommendations, pricing, selected_testimonials      (jak w v3)
recommendations ──< recommendation_packages, selected_*         (jak w v3)

employees ──< leads, sale_opportunities, meetings, tasks, task_templates   owner / assignee
employees ──< absences >──< employees                                      zastępstwa

projects ──< tasks >── task_templates
pricing, document_templates, materials, newsletter_stats, katalogi pakietów — bez zmian
```

---

## Inwentarz tabel

| Tabela | Status | Uwagi |
|---|---|---|
| `persons` | **NOWA** | jedyna tabela osób (klienci i kontakty) |
| `sale_opportunities` | **NOWA** | kanban po `stage`; wzięła z `leads` etapy, wartość, utratę |
| `sale_opportunity_stage_history` | **NOWA** | jeden wiersz na zmianę etapu |
| `employees` | **NOWA** | zespół CoAction, źródło e-maili |
| `absences` | **NOWA** | nieobecności i zastępstwa |
| `leads` | zmieniona | odchudzona; M2M do `persons` |
| `meetings` | zmieniona | link do szansy, `attendees`, `owner` → `employees` |
| `assessments` | zmieniona | należy do `persons`; +2 pola |
| `recommendations` | zmieniona | należy do `persons` |
| `offers` | zmieniona | link do `sale_opportunities` zamiast `leads`; usunięte `template_name` (szablon przez istniejący link `document_templates`); status `approved` |
| `tasks`, `task_templates` | zmienione | `assignee` → `employees`; `tasks` +linki do rekordu, którego dotyczą |
| `activities` | zmieniona | +link do `sale_opportunities` |
| `companies` | zmieniona | nowe relacje; opis |
| `participants` | **USUNIĘTA** | rola przechodzi w pola `sale_opportunities` |
| `document_templates`, `materials`, `newsletter_stats`, `pricing`, `projects`, `testimonials`, `training_descriptions`, `package_core_slides`, `package_variants_cores`, `package_variants_adons`, `recommendation_packages`, `selected_package_variants_cores`, `selected_package_variants_adons` | bez zmian | pola i relacje jak w `scripts/init-schema.py` |

Razem: 27 tabel (było 23: +5 nowych, −1 usunięta).

---

## 1. `persons` — NOWA

Każdy człowiek spoza zespołu CoAction, jeden wiersz na osobę. Klucz dedupu:
`email` (W4 szuka po nim). Pole tytułowe: `full_name`.

| Pole | Typ | Uwagi |
|---|---|---|
| `full_name` | SingleLineText | tytuł wiersza |
| `email` | Email | klucz dedupu |
| `phone` | PhoneNumber | |
| `position` | SingleLineText | było `participants.position` |
| `linkedin_url` | URL | było `participants.linkedin_url` |
| `industry` | SingleSelect (INDUSTRY) | dla B2C bez firmy; było `leads.industry` |
| `role_context` | LongText | było `participants.role_context` |
| `frequency` | SingleSelect `codziennie` / `kilka_razy_w_tyg` / `rzadko` | było `participants.frequency` |
| `assigned_methodologist` | link → `employees` | było polem `User` w `participants` |
| `sales_mode` | SingleSelect `Standard` / `Tylko spotkania` | **nowe**; puste = `Standard` (NocoDB nie ustawi domyślnej opcji, więc flow traktują puste jak Standard). `Tylko spotkania` = osoba, która nigdy nie będzie leadem ani kupującym (np. księgowa, specjalista, osoba z obsługi): ma tylko tworzyć spotkania po umówieniu się. Ustawia zespół ręcznie na osobie |
| `new_opportunity_status`, `new_opportunity_note` | SingleSelect `generating` / `done` / `error`, LongText | **nowe**: feedback przycisku „Utwórz szansę sprzedaży” na osobie (W21) |
| przycisk **„Utwórz szansę sprzedaży”** | Button | **nowy**: tworzy szansę dla znanej osoby bez nowego leada (klient powracający, kontynuacja, upsell); typ wylicza W20; szansa wskazuje pierwotny lead osoby |
| `notes` | LongText | trwałe notatki o osobie |
| `legacy_id` | Number | tylko jeśli import będzie łączył osoby |

Relacje (pola właściciela): `possible_duplicate` (M2M → `persons`),
`bought_opportunities` (→ `sale_opportunities`), `assessments`,
`recommendations`, `tasks`. Pola zwrotne (nadaje NocoDB, nazwy docelowe):
`company`, `leads`, `participant_in`, `audited_in`, `attended_meetings`.

Zmiana pracy = przepięcie `company`; historii zatrudnienia nie prowadzimy.

**`sales_mode` = `Tylko spotkania`.** Każdy flow, który tworzy leada lub szansę,
pomija takie osoby; spotkanie i uczestnik (`meetings.attendees`) powstają jak
zwykle, ale bez linku do szansy:

- **formularz (W4):** nie tworzy leada, tylko wpis w `activities`;
- **rezerwacja (cal.com):** tworzy `meetings` i `attendees`, nie linkuje do żadnej
  szansy i nie tworzy leada (dotyczy też ewentualnego tworzenia leada dla
  nieznanego uczestnika rezerwacji, tak jak proces z `opis_procesu_workflow.md`
  §1 zakłada: bookings zasilają leady);
- **konwersja lead → szansa:** odmawia, gdy `primary_person` ma ten tryb;
- osoby w trybie `Tylko spotkania` nie powinny trafiać do `leads.persons`,
  `to_be_audited` ani `participants`; NocoDB tego nie wymusi, więc pilnują flow
  i widok kontrolny „Osoby tylko do spotkań".

## 2. `leads` — odchudzona

Zgłoszenie i jego kwalifikacja. Brak etapów sprzedaży i wartości.

| Pole | Typ | Zmiana |
|---|---|---|
| `lead_name` | SingleLineText | bez zmian (np. „Acme – audyty dla 3 pracowników") |
| `persons` | link M2M → `persons` | **nowe**, min. 1 osoba (lead = osoba lub grupa osób) |
| `company` | zwrotne od `companies.leads` | bez zmian |
| `owner` | link → `employees` | było `User` |
| `received_at` | DateTime | **nowe** (data wpłynięcia, import) |
| `lead_type` | SingleSelect `B2C` / `B2B` | bez zmian |
| `lead_source` | SingleSelect | bez zmian |
| `contact_channel` | SingleSelect | bez zmian |
| `qualification` | SingleSelect `unqualified` / `non-MQL` / `MQL` / `non-SQL` / `SQL` | bez zmian |
| `disqualify_reason`, `disqualify_note` | SingleSelect, LongText | bez zmian |
| `company_match_status` | SingleSelect | bez zmian (W4v2 / W5) |
| `primary_person` | zwrotne od `persons.primary_in_leads` | **nowe**, 0..1; główny kontakt leada (domyślnie osoba, która wypełniła formularz; ustawia W4). Musi być jedną z `persons` leada. Z niej konwersja bierze `sale_opportunities.person` |
| `convert_status`, `convert_note` | SingleSelect `generating` / `done` / `error`, LongText | **nowe**, feedback przycisku konwersji (`gen_status_field("convert", …)`); błąd, gdy brak `primary_person` albo główny kontakt ma tryb „Tylko spotkania”; po sukcesie notatka z liczbą szans leada |
| `notes`, `legacy_id` | LongText, Number | bez zmian; `notes` = trwałe notatki o leadzie (akcja z terminem to zadanie) |
| przycisk **„Utwórz szansę sprzedaży"** | Button | **nowy**, placeholder jak pozostałe, webhook do flow konwersji; flow czyta `primary_person` |

**Usunięte** (przechodzą do `sale_opportunities` lub `persons`): `contact_email`,
`contact_phone`, `industry`, `stage`, `state`, `loss_reason`, `loss_note`,
`deal_value`, `label`, `offer_prep_status`, `training_goals`, `offer_sent_at`,
`contract_sent_at`, `closed_at`, `possible_duplicate`.

Relacje: `opportunities` (→ `sale_opportunities`), `tasks`, `activities`.
Usuwane: relacje do `participants`, `meetings`, `offers`.

## 3. `sale_opportunities` — NOWA

Szansa sprzedaży. Należy do osoby i firmy, nie do leada. Pole tytułowe: `name`.

| Pole | Typ | Uwagi |
|---|---|---|
| `name` | SingleLineText | np. „Acme – audyty i kurs" |
| `person` | zwrotne od `persons.bought_opportunities` | **wymagane**: kupujący B2C albo główny kontakt B2B |
| `company` | zwrotne od `companies.opportunities` | 0..1, dla B2B |
| `source_lead` | zwrotne od `leads.opportunities` | 0..1; lead, z którego szansa powstała. Jeden lead może mieć wiele szans (kolejne zakupy, równoległe działy) |
| `segment` | SingleSelect `B2C` / `B2B` | było `leads.lead_type` |
| `owner` | link → `employees` | było `User` |
| `stage` | SingleSelect | lista z A1 |
| `state` | SingleSelect `open` / `won` / `lost` / `archived` | |
| `loss_reason` | SingleSelect `cena` / `brak_decyzji` / `konkurencja` / `przesuniete_w_czasie` / `inne` | z `leads` |
| `loss_note` | LongText | z `leads` |
| `deal_value` | Currency PLN | **prognoza**, nie `offers.total_price` (opis jak w v3) |
| `opportunity_type` | SingleSelect `Nowy klient` / `Kontynuacja` / `Upsell` / `Powrót po przerwie` | A15; wylicza W20 przy tworzeniu szansy (W14 z leada, W21 z osoby), potem bez zmian |
| `campaign` | SingleSelect, lista należy do zespołu (start: „Black Week”) | było `label` z `leads`, A4; skrypt ustawia opcje tylko na pustym polu i ich nie nadpisuje |
| `offer_prep_status` | SingleSelect `none` / `waiting_goals` / `goals_provided` / `testimonials_provided` / `draft_ready` | z `leads` (W1 / W6b) |
| `training_goals` | LongText | z `leads` |
| `offer_sent_at`, `contract_sent_at`, `closed_at` | Date | z `leads`, pisze wyłącznie n8n |
| `stage_changed_at` | DateTime | **nowe** (A13); pisze W2 przy każdej zmianie etapu; podstawa widoku „Utknięte" |
| `service_end_date` | Date | **nowe**, A5 |
| `to_be_audited` | link M2M → `persons` | kto czeka na audyt; A10 |
| przycisk **„Generuj zadania audytowe"** | Button | **nowy**, patrz niżej |
| `audit_tasks_status`, `audit_tasks_note` | SingleSelect `generating` / `done` / `error`, LongText | feedback przycisku (`gen_status_field("audit_tasks", …)` jak przy `materials`); błąd w `audit_tasks_note` |
| `audit_scope` | LongText | **nowe**, A9: zakres audytu (które sytuacje komunikacyjne sprawdzić, jakie zadanie audytowe); wpisuje metodyczka przy zadaniu „Przygotuj audyt" |
| `notes`, `legacy_id` | LongText, Number | `notes` = trwałe notatki o szansie (kontekst, ustalenia); akcja z terminem to zadanie |

Relacje (pola właściciela): `participants`, `to_be_audited`, `audited`
(wszystkie M2M → `persons`), `history`, `meetings`, `tasks`, `activities`, `offers`.

- `participants` wypełnia się przy podpisaniu umowy. Dla B2C kupujący jest
  swoim własnym participantem.
- `to_be_audited` uzupełnia handlowiec (B2B) albo n8n (B2C: kupujący).
  Osoby muszą już istnieć w `persons` (z firmą i e-mailem); tworzenie osób z
  listy podanej przez HR pozostaje ręczne, patrz „Ryzyka".
- `audited` dopisuje n8n przy utworzeniu oceny (`assessments`) i jednocześnie
  usuwa osobę z `to_be_audited` (A10).
- **Przycisk „Generuj zadania audytowe"** (flow idempotentny): dla każdej osoby
  z `to_be_audited`, która nie ma otwartego zadania z `task_type` =
  `audit_prep` i linkami do tej szansy i osoby, tworzy zadanie (adresat i linki: sekcja
  „Zasady tworzenia zadań"). Ponowne kliknięcie po dopisaniu kolejnych osób
  tworzy tylko brakujące. Stan pokazuje `audit_tasks_status`.
- Jeden lead może mieć wiele szans, więc `source_lead` nie jest unikalne. Dubla
  (np. dwukrotne kliknięcie przycisku) NocoDB nie wykryje; W14 zapisuje w
  `convert_note` liczbę szans leada, żeby było to widać.

## 4. `sale_opportunity_stage_history` — NOWA

Jeden wiersz na zmianę etapu. Pisze wyłącznie n8n (W2) oraz import. Pole
tytułowe: `title` (np. „Audyt → Demo").

| Pole | Typ | Uwagi |
|---|---|---|
| `title` | SingleLineText | |
| `sale_opportunity` | zwrotne od `sale_opportunities.history` | |
| `from_stage` | SingleSelect | puste dla pierwszego wpisu; te same opcje co `stage` |
| `to_stage` | SingleSelect | te same opcje co `stage` |
| `changed_at` | DateTime | dla importu: data z Excela |
| `changed_by` | SingleLineText | `n8n:W2`, `import` albo użytkownik |

Lista opcji `stage` / `from_stage` / `to_stage` musi być jedną stałą w
`init-schema.py` (jak `VARIANT` w v3), inaczej się rozjadą.

## 5. `employees` — NOWA

Zespół CoAction. Klienci i kontakty to `persons`, pracownicy to ta tabela:
inny cykl życia, inni odbiorcy (powiadomienia, zadania) i brak powodu, żeby
pracownicy trafiali na listy klientów albo do eksportów marketingowych.

| Pole | Typ | Uwagi |
|---|---|---|
| `full_name` | SingleLineText | tytuł |
| `email` | Email | źródło adresów do powiadomień (W2, W3, W0) i przypisywania zadań |
| `role` | SingleSelect `handlowiec` / `metodyczka` / `finanse` / `marketing` / `admin` | |
| `is_active` | Checkbox | domyślnie zaznaczone |

Relacje (pola właściciela): `absences`, `leads`, `opportunities`, `meetings`,
`tasks`, `task_templates`, `assigned_persons`. Pola zwrotne: `covers_absences`.

## 6. `absences` — NOWA

| Pole | Typ | Uwagi |
|---|---|---|
| `title` | SingleLineText | np. „Przemek – urlop" |
| `employee` | zwrotne od `employees.absences` | kto jest nieobecny |
| `absence_type` | SingleSelect `urlop` / `L4` / `inne` | |
| `start_date`, `end_date` | Date | |
| `substitutes` | link M2M → `employees` | kto zastępuje (może być kilka osób) |

Reguła zastępstwa (w n8n, nie w bazie):

1. Flow wylicza odpowiedzialnego z roli (np. `owner` szansy, metodyczka
   audytu).
2. Jeśli w dniu zadania (`due_date`; dla zadań natychmiastowych: dziś) ma on
   wiersz w `absences`, który ten dzień obejmuje, `assignee` = pierwszy z
   `substitutes`, który sam nie jest wtedy nieobecny.
3. Brak wolnego zastępcy: zadanie dostaje użytkownik z rolą `admin` i
   powiadomienie.

## 7. `meetings` — zmiany

| Zmiana | |
|---|---|
| `owner` | link → `employees` (było `User`) |
| `sale_opportunity` | zwrotne od `sale_opportunities.meetings`; **0..1**, bo spotkanie może być przed powstaniem szansy |
| `attendees` | link M2M → `persons`; kto był na spotkaniu |
| `external_id` | SingleLineText, **nowe**; `uid` rezerwacji z cal.com, klucz dedupu flow rezerwacji i powiązania przy zmianie terminu / anulowaniu. Brakowało go w v3 i w `init-schema.py` |
| relacja do `leads` | **usunięta** |
| relacja do `participants` | **usunięta** (zastąpiona przez `attendees`) |

Pozostałe pola (`goals`, `challenges`, `ai_status` itd.) bez zmian.

## 8. `assessments` — zmiany

| Zmiana | |
|---|---|
| `person` | zwrotne od `persons.assessments`; zastępuje link do `participants`. Ocena należy do osoby, więc historia jej poziomu jest dostępna między szansami |
| `self_assessment` | LongText, **nowe** (było `participants.self_assessment`) |
| `manager_needs` | LongText, **nowe** (było `participants.manager_needs`) |

Relacja do `meetings` i pozostałe pola (`cefr_*`, `strengths`, `gaps`,
`needs_summary`, `ai_status`, przycisk) bez zmian. Utworzenie oceny dopisuje
osobę do `sale_opportunities.audited` (n8n).

## 9. `recommendations`, `offers`, `tasks`, `task_templates`, `activities`, `companies`

- **`recommendations`**: `person` (zwrotne od `persons.recommendations`)
  zastępuje link do `participants`. Rekomendacja jest powiązana z ofertą
  (`offers` → `recommendations`, relacja ma-wiele, istnieje dziś w
  `init-schema.py`), a oferta ze szansą (`sale_opportunities` → `offers`,
  zastępuje `leads` → `offers`): łańcuch rekomendacja → oferta → szansa
  zostaje, rollupy bez zmian. Osobnego linku rekomendacji do szansy nie
  dodajemy. Konsekwencja relacji has-many: rekomendacja należy do **jednej**
  oferty. Nowa wersja oferty dla innego podzbioru osób dostaje własne wiersze
  rekomendacji (kopie), a nie współdzieli istniejące; tak już działa W1
  („jeden lead ma kilka ofert dla różnych podzbiorów uczestników").
- **`offers`**: link do `sale_opportunities` (`sale_opportunities.offers`)
  zastępuje link do `leads`. `status`: `draft` → **`approved`** (zatwierdzona do
  wysłania, nowy stan) → `sent` → `accepted` / `rejected`. Szablon oferty to
  istniejący link `document_templates` (relacja `document_templates` →
  `offers`, bez zmian; W1 czyta go dziś); pole tekstowe `template_name` jest
  **usunięte**. Nowe (A14): `approved_total` (Currency; n8n zapisuje w nim
  wartość `total_price` w chwili przejścia na `approved`, potem się nie zmienia)
  oraz przycisk **„Utwórz nową wersję"** z polami `version_status` /
  `version_note` (`gen_status_field("version", …)`): kopiuje ofertę (`version` + 1,
  `status` = `draft`) razem z jej rekomendacjami i ich wierszami
  `selected_package_variants_*`, więc wersje nigdy nie współdzielą
  rekomendacji; w nowej wersji usuwa się rekomendacje osób, które odpadły.
  Przejście na `approved` aktualizuje też `sale_opportunities.deal_value`.
  Pozostałe pola i rollup `total_price` bez zmian.
- **`tasks`**: `assignee` jako link → `employees` (było `User`). Nowe pole
  `task_type` (SingleSelect, wartości w „Zasady tworzenia zadań"): jedyny
  sposób, w jaki flow rozpoznają rodzaj zadania. Linki do
  rekordu, którego dotyczy zadanie (wszystkie opcjonalne; zadanie wskazuje
  rekord, z którego można je wykonać): `lead`, `person`, `sale_opportunity`,
  `meeting`, `assessment`, `recommendation`, `offer`. Zasady tworzenia: sekcja
  „Zasady tworzenia zadań". Nowe (A13): `scheduled_for` (Date, „zaplanowane
  na": kiedy zająć się zadaniem lub wykonać akcję, np. „odezwać się za 3
  dni"; `due_date` zostaje terminem ostatecznym) oraz opcja `scheduled` w
  `status`: `scheduled` (czeka na datę `scheduled_for`) → `todo` →
  `in_progress` → `done` / `cancelled`. Zadanie `scheduled` nie wchodzi do
  widoków „do zrobienia", dopóki nie nadejdzie jego data.
- **`task_templates`**: `assignee` jako link → `employees`.
- **`activities`**: dodany link do `sale_opportunities`; link do `leads`
  zostaje.
- **`companies`**: relacje do `persons` i `sale_opportunities`; usunięta do
  `participants`. Opis tabeli („lead to pojedyncza szansa") poprawić na
  „szansa sprzedaży".

---

## Relacje do utworzenia (docelowa lista `RELATIONS`)

Tylko zmienione i nowe. Pozostałe z `init-schema.py` zostają bez zmian
(katalogi pakietów, `offers`↔`pricing`/`selected_testimonials`/
`recommendations`, `document_templates`, `projects`, `task_templates`↔`tasks`,
`tasks`↔`activities`, `meetings`↔`activities`, `recommendations` ↔
`recommendation_packages` / `selected_*`).

| Z tabeli | Pole | Typ | Do tabeli | Pole zwrotne (nazwa docelowa) |
|---|---|---|---|---|
| `companies` | `persons` | has-many | `persons` | `company` |
| `companies` | `opportunities` | has-many | `sale_opportunities` | `company` |
| `companies` | `leads` | has-many | `leads` | `company` (bez zmian) |
| `leads` | `persons` | many-to-many | `persons` | `leads` |
| `leads` | `opportunities` | has-many | `sale_opportunities` | `source_lead` |
| `leads` | `tasks` | has-many | `tasks` | bez zmian |
| `leads` | `activities` | has-many | `activities` | bez zmian |
| `persons` | `possible_duplicate` | many-to-many | `persons` | (symetryczne) |
| `persons` | `bought_opportunities` | has-many | `sale_opportunities` | `person` |
| `persons` | `assessments` | has-many | `assessments` | `person` |
| `persons` | `recommendations` | has-many | `recommendations` | `person` |
| `persons` | `tasks` | has-many | `tasks` | `person` |
| `sale_opportunities` | `participants` | many-to-many | `persons` | `participant_in` |
| `sale_opportunities` | `to_be_audited` | many-to-many | `persons` | `to_be_audited_in` |
| `sale_opportunities` | `audited` | many-to-many | `persons` | `audited_in` |
| `sale_opportunities` | `history` | has-many | `sale_opportunity_stage_history` | `sale_opportunity` |
| `sale_opportunities` | `meetings` | has-many | `meetings` | `sale_opportunity` |
| `sale_opportunities` | `tasks` | has-many | `tasks` | `sale_opportunity` |
| `sale_opportunities` | `activities` | has-many | `activities` | `sale_opportunity` |
| `sale_opportunities` | `offers` | has-many | `offers` | `sale_opportunity` |
| `meetings` | `attendees` | many-to-many | `persons` | `attended_meetings` |
| `meetings` | `assessments` | has-many | `assessments` | bez zmian |
| `employees` | `absences` | has-many | `absences` | `employee` |
| `absences` | `substitutes` | many-to-many | `employees` | `covers_absences` |
| `employees` | `leads` | has-many | `leads` | `owner` |
| `employees` | `opportunities` | has-many | `sale_opportunities` | `owner` |
| `employees` | `meetings` | has-many | `meetings` | `owner` |
| `meetings` | `tasks` | has-many | `tasks` | `meeting` |
| `assessments` | `tasks` | has-many | `tasks` | `assessment` |
| `recommendations` | `tasks` | has-many | `tasks` | `recommendation` |
| `offers` | `tasks` | has-many | `tasks` | `offer` |
| `employees` | `tasks` | has-many | `tasks` | `assignee` |
| `employees` | `task_templates` | has-many | `task_templates` | `assignee` |
| `employees` | `assigned_persons` | has-many | `persons` | `assigned_methodologist` |
| `persons` | `primary_in_leads` | has-many | `leads` | `primary_person` |

**Usunięte relacje:** `companies`→`participants`, `leads`→`participants`,
`leads`→`meetings`, `leads`→`offers`, `leads`↔`leads` (`possible_duplicate`),
`participants`→`assessments`, `participants`→`recommendations`,
`participants`↔`meetings`.

> **Typ pola i nazwy pól zwrotnych.** `init-schema.py` tworzy relacje jako
> `Links` (v1), a `scripts/upgrade-links.py` konwertuje je do
> `LinkToAnotherRecord` (v3, z fizyczną tabelą łączącą). NocoDB sam nadaje
> nazwy polom zwrotnym; kod w `scripts/demo-schema-init.py` łapie nowe pole
> zaraz po utworzeniu każdej relacji i próbuje je przemianować na nazwę
> docelową z kolumny „Pole zwrotne". Kiedy tabela jest celem kilku relacji z
> tego samego właściciela (np. `participants`, `to_be_audited` i `audited` →
> `persons`), tylko
> takie jednoprzebiegowe podejście je rozróżnia. Rename po konwersji nie był
> sprawdzony na żywo; po `make init-schema` sprawdź nazwy w UI.

---

## Mapowanie starych pól

| Stare pole | Nowe miejsce |
|---|---|
| `leads.lead_name` | `leads.lead_name` oraz `sale_opportunities.name` |
| `leads.contact_email`, `contact_phone` | `persons.email`, `persons.phone` |
| `leads.lead_type` | `leads.lead_type` oraz `sale_opportunities.segment` |
| `leads.owner` | `leads.owner` (link), `sale_opportunities.owner` |
| `leads.industry` | `persons.industry` (B2C) / `companies.industry` (B2B) |
| `leads.stage`, `state` | `sale_opportunities.*` |
| `leads.loss_reason`, `loss_note` | `sale_opportunities.*` |
| `leads.deal_value` | `sale_opportunities.deal_value` |
| `leads.label` („typ szansy” z Excela: Nowy klient, Upsell, Odnowienie…) | brak odpowiednika; `sale_opportunities.campaign` to inne pojęcie (kampania) |
| `leads.offer_prep_status`, `training_goals` | `sale_opportunities.*` |
| `leads.offer_sent_at`, `contract_sent_at`, `closed_at` | `sale_opportunities.*` |
| `leads.possible_duplicate` | `persons.possible_duplicate` |
| `participants.full_name`, `email`, `position`, `linkedin_url` | `persons.*` |
| `participants.role_context`, `frequency` | `persons.*` |
| `participants.assigned_methodologist` | `persons.assigned_methodologist` (link → `employees`) |
| `participants.self_assessment`, `manager_needs` | `assessments.*` |
| `tasks.assignee`, `task_templates.assignee` (User) | link → `employees` |
| `offers.template_name` (SingleLineText) | usunięte; szablon wskazuje istniejący link `offers.document_templates` |

---

## Wpływ na flow

Liczba odwołań do `leads` / `participants` w JSON-ach `docs/archive/fable/`
(liczone grepem, nie przeglądem treści):

| Flow | `leads` | `participants` | Co się zmienia |
|---|---|---|---|
| W1 generate_offer | 14 | 11 | czyta z `sale_opportunities`; kupujący z `person`; osoby oferty z `recommendations.person`; szablon nadal z linku `offers.document_templates`; `template_name` flow nie czyta, występuje tylko w opisach kolumn węzłów NocoDB (odświeżyć po usunięciu pola) |
| W4v2 intake_matching | 9 | 0 | dopasowuje / tworzy `persons`, tworzy `leads` (nie szansę); ustawia `primary_person` na osobę z formularza; pomija osoby z `sales_mode` = `Tylko spotkania` (bez leada, tylko wpis w `activities`) |
| W4v3 cf7_intake | 6 | 5 | jw.; osoba trafia tylko do `persons` |
| W8 assessment_needs_summary | 3 | 10 | ścieżka `assessments.person` + `meetings`; szansa przez spotkanie |
| W2 stage_change | 2 | 0 | działa na `sale_opportunities`, dopisuje `sale_opportunity_stage_history` i ustawia `stage_changed_at`; krok „Notify owner" czyta adres z `employees` |
| W5 company_dedup | 2 | 0 | do sprawdzenia; ewentualnie dedup `persons` |
| W6b offer_pipeline | 2 | 0 | `sale_opportunities` |
| W13 lead_inquiry_analysis | 2 | 0 | aktualizuje `leads` zmiennym zestawem pól (patch): **sprawdzić, które pola zapisuje**; część mogła przejść do `persons` / `sale_opportunities` |
| W7 bookings_meetings_sync | 1 | 1 | zastąpiony nowym flow zasilanym webhookami cal.com (patrz „Rezerwacje cal.com" niżej) |
| W9 offer_package_texts | 1 | 0 | `sale_opportunities` |
| W3 task_notifications, W0 recurring_tasks | 0 | 0 | wysyłają e-maile; adres z `employees.email`, zastępca z `absences`. Skąd biorą adres dziś: do sprawdzenia |
| NOWY | | | konwersja lead → szansa (przycisk na `leads`); typ szansy z W20 |
| NOWY | | | W20: wyliczenie `opportunity_type` (podflow) |
| NOWY | | | W21: szansa dla znanej osoby bez nowego leada (przycisk na `persons`) |
| NOWY | | | „Generuj zadania audytowe" (przycisk na `sale_opportunities`) |
| NOWY | | | przeniesienie `to_be_audited` → `audited` przy utworzeniu oceny |
| NOWY | | | dzienne przypomnienie o niezatwierdzonych szkicach AI (przypadek 3) |
| NOWY | | | przejście oferty na `approved`: zapis `approved_total` i aktualizacja `sale_opportunities.deal_value` |
| NOWY | | | „Utwórz nową wersję" oferty (kopia rekomendacji z `selected_package_variants_*`) |
| NOWY | | | dzienne uruchamianie zadań zaplanowanych: `status` = `scheduled` i `scheduled_for` ≤ dziś → `todo` + powiadomienie do `assignee` z regułą zastępstwa. Do sprawdzenia, co dziś wyzwala W3 (task_notifications) i czy da się go użyć zamiast nowego flow |
| W2 stage_change (rozszerzenie) | | | zadania przy przejściach z tabeli w „Zasady tworzenia zadań"; istniejące zadanie „fill reason" przy `lost` bez powodu: do przeglądu, bo nie mieści się w trzech przypadkach |
| W6a, W10, W11 | 0 | 0 | bez zmian w treści; ID po odświeżeniu schematu |

Po zmianie schematu: `make dump-crm-schema` i przegląd hardkodowanych ID w
każdym flow (`.ai/rules/nocodb.md` §1).

**Rezerwacje cal.com (zastępują W7 z MS Bookings).** Dotychczasowy W7 co 15
minut czytał jeden kalendarz Outlooka przez Graph, brał pierwszego uczestnika,
nie ustawiał `meeting_type`, nie tworzył osób i nie obsługiwał zmian terminu ani
anulowania. Nowy flow startuje z webhooków cal.com i nie ma tych ograniczeń:

- **Wyzwalacze:** utworzenie, zmiana terminu i anulowanie rezerwacji.
  Webhook trzeba ustawić na każdym typie wydarzenia (albo na poziomie zespołu)
  osobno dla każdej metodyczki i handlowca, których rezerwacje mają trafiać do
  CRM.
- **Brak opóźnienia:** spotkanie pojawia się w CRM od razu, bez pętli co 15 min.
- **Uczestnicy:** wszyscy uczestnicy rezerwacji → `persons` po e-mailu i link
  `attendees`; nieznany e-mail → minimalny wiersz `persons` (imię, e-mail)
  oznaczony jako możliwy duplikat.
- **Właściciel spotkania:** `meetings.owner` z e-maila organizatora rezerwacji
  dopasowanego do `employees.email`.
- **`meeting_type`** z `eventTypeId` rezerwacji przez stałe mapowanie w flow
  (np. „Discovery" → `discovery`, „Audyt" → `audit`, „Demo" → `demo`).
  Mapowanie jest deterministyczne, tytuł rezerwacji nie ma znaczenia (zasada
  „Tytuł jest dla zespołu"). Nowy typ wydarzenia spoza mapowania zostawia pole
  puste; zespół ustawia je w widoku „Spotkania bez typu" i dopisuje mapowanie.
- **Zmiany:** zmiana terminu aktualizuje `starts_at` / `ends_at`, anulowanie
  ustawia `status` = `cancelled` (rozpoznanie po `external_id` = `uid`
  rezerwacji; przy zmianie terminu cal.com tworzy nową rezerwację powiązaną ze
  starą, więc flow musi użyć identyfikatora poprzedniej).
- **Szansa:** spotkanie linkowane do jedynej otwartej szansy osoby, gdzie
  „szansa osoby" to szansa, w której osoba jest kupującym
  (`bought_opportunities`), na liście `to_be_audited` (`to_be_audited_in`) albo
  wśród `participants` (`participant_in`); przy zero lub wielu zostaje bez
  linku. Osoby z `sales_mode` = `Tylko spotkania` zawsze zostają bez linku do
  szansy i bez leada.
- **Opcjonalnie (do sprawdzenia w używanej instancji cal.com):** link do
  rezerwacji audytu generowany jako formuła na szansie, z identyfikatorem
  szansy i e-mailem osoby w parametrach adresu, żeby powiązanie ze szansą było
  jednoznaczne zamiast zgadywane.
- **Poza cal.com:** wydarzenie wpisane bezpośrednio w kalendarzu nie wywołuje
  webhooka. Wtedy spotkanie wpisuje się ręcznie w NocoDB (fallback) albo
  metodyczka rezerwuje je w cal.com w imieniu klienta.

Flow rezerwacji **nie zamyka** zadań „Przygotowanie audytu": zadanie obejmuje
przygotowanie, które trwa do audytu, więc zamyka je metodyczka.

**Konwersja lead → szansa** (nowy flow, idempotentny):

- nie blokuj, gdy lead ma już szanse (wiele szans na lead jest dozwolone); policz je do notatki,
- odmów (błąd w `convert_status` / `convert_note`), gdy `primary_person` ma
  `sales_mode` = `Tylko spotkania`,
- utwórz `sale_opportunities`: `person` = `leads.primary_person` (bez
  niej flow kończy się błędem w `convert_status` / `convert_note`), `company`, `segment`, `owner`, `source_lead`, `stage` = `new`,
  `state` = `open`, `name`,
- zapisz pierwszy wiersz w `sale_opportunity_stage_history`.

Zadania nie tworzy (ten sam handlowiec, szansa widoczna na kanbanie), zgodnie z
sekcją „Zasady tworzenia zadań".

---

## Nazwy etapów (A1)

Opcje `stage` (oraz `from_stage` / `to_stage`) mają nazwy po polsku. Klucze
techniczne w tej specyfikacji (kolumna lewa) są stałe, flow porównują dokładnie
nazwy z prawej kolumny. Propozycja, do potwierdzenia:

| Klucz | Nazwa opcji w NocoDB |
|---|---|
| `new` | Nowa |
| `discovery_scheduled` | Discovery umówione |
| `discovery_done` | Discovery odbyte |
| `audit` | Audyt |
| `recommendation` | Rekomendacja / demo |
| `offer_sent` | Oferta wysłana |
| `offer_discussed` | Omówienie oferty |
| `contract_sent` | Umowa wysłana |
| `contract_signed` | Umowa podpisana |
| `lost` | Utracona |
| `archived` | Zarchiwizowana |

**Nie zmieniamy nazw opcji SingleSelect w UI bez zmiany flow**: flow
porównują ich wartości, więc przemianowanie opcji po cichu zepsuje
automatyzację.

## Widoki NocoDB do skonfigurowania

Widoków nie tworzy skrypt; to checklista do odtworzenia po `make init-schema`.

| Widok | Tabela | Konfiguracja |
|---|---|---|
| Pipeline | `sale_opportunities` | Kanban po `stage`, `state` = open; na karcie `owner`, `deal_value`, `stage_changed_at` |
| Moje zadania (do zrobienia) | `tasks` | jeden widok na osobę: `assignee` = osoba, `status` ∈ todo / in_progress **lub** (`status` = scheduled i `scheduled_for` ≤ dziś); grupa filtrów z alternatywą |
| Moje zaplanowane | `tasks` | `assignee` = osoba, `status` = scheduled, sort po `scheduled_for` |
| Utknięte | `sale_opportunities` | `state` = open, `stage_changed_at` starsze niż 14 dni, `stage` ∈ Oferta wysłana / Omówienie oferty / Umowa wysłana |
| Leady do zakwalifikowania | `leads` | `qualification` ∈ unqualified / MQL, sort po `received_at` |
| Audyty w toku | `sale_opportunities` | `stage` = Audyt; na karcie `to_be_audited`, `audited`, `participants` |
| Oferty do wysłania | `offers` | `status` = approved |
| Szkice AI do zatwierdzenia | `meetings`, `assessments`, `recommendations` | `ai_status` = ai_draft_ready |
| Spotkania bez typu | `meetings` | `meeting_type` puste |
| Osoby tylko do spotkań | `persons` | `sales_mode` = Tylko spotkania; kontrola, czy nie są w `leads.persons`, `to_be_audited` ani `participants` |

Filtry względne po datach (dziś, „starsze niż N dni") do sprawdzenia w
używanej wersji NocoDB.

## Do sprawdzenia w praktyce (wejdą do planu migracji)

Rzeczy, których nie da się rozstrzygnąć na papierze; sprawdzamy je na działającej
instancji i dopiero wtedy utrwalamy decyzję:

1. **Link do rezerwacji audytu z parametrami** (pomysł do wypróbowania):
   formuła na `sale_opportunities`, która buduje adres rezerwacji cal.com z
   identyfikatorem szansy i e-mailem osoby, tak by flow rezerwacji wiązał
   spotkanie ze szansą jednoznacznie, a nie zgadywał po „jedynej otwartej".
   Sprawdzić, czy cal.com w chmurze przekazuje takie parametry do webhooka
   (pola rezerwacji / metadane) i czy da się je wstępnie wypełnić w URL.
2. **Webhooki cal.com w chmurze:** które wyzwalacze są dostępne w używanym
   planie (utworzenie, zmiana terminu, anulowanie), jak wygląda ładunek, czy
   da się je ustawić na poziomie zespołu.
3. **Przemianowanie pól zwrotnych relacji** po konwersji do v3 (kod z
   `scripts/demo-schema-init.py`, niezweryfikowane na żywo).
4. **Filtry względne po datach** w widokach (dziś, „starsze niż N dni") i
   grupy filtrów z alternatywą (widok „Moje zadania (do zrobienia)").
5. **Co dziś wyzwala W3** i skąd W2 / W3 / W0 biorą adres e-mail odbiorcy.
6. **Które pola zapisuje W13** na leadzie.

## Ryzyka i luki

- **Widoki „moje zadania".** NocoDB filtruje „bieżący użytkownik" tylko po
  polu `User`. Z linkiem do `employees` potrzeba jednego widoku na osobę
  (A6). Alternatywa: zostawić `User` obok linku wyłącznie do filtrów UI, ale to
  dwa pola do pilnowania.
- **Szansa bez leada** (np. wpisana ręcznie dla klienta powracającego) nie
  dziedziczy osób z procesu decyzyjnego ani źródła; kolejne szanse klienta
  powinny wskazywać jego pierwotny lead.
- **Rola osoby w leadzie.** `leads.persons` nie rozróżnia decydenta, HR i
  finansów. Jeśli to będzie potrzebne, dojdzie tabela łącząca; na UAT
  wystarcza `persons.position`.
- **Brak statusu kandydata.** Nie da się śledzić osoby, która nie ma jeszcze
  zaplanowanego spotkania. Lista osób do audytu żyje w `audit_scope` i w
  zadaniu „Przygotuj audyt"; wchodzą do `audited` dopiero po utworzeniu oceny.
- **Zgłoszenie od osoby w trybie `Tylko spotkania`.** Formularz takiej osoby
  nie tworzy leada ani zadania, tylko wpis w `activities`, więc jeśli jej
  wiadomość wymagała reakcji, nikt jej nie zobaczy. Do rozważenia: osobny
  przypadek zadania albo powiadomienie do `admin`.
- **Typ szansy zależy od `service_end_date`.** Reguła A15 liczy koniec usługi z
  `service_end_date`, a gdy go brak, z `closed_at` (data podpisania). Jeśli nikt
  nie wpisze końca usługi, kolejna szansa klienta może dostać zły typ
  (np. Kontynuacja zamiast Upsellu przy trwającej usłudze). Nic nie pilnuje
  wypełnienia tego pola.
- **Import ze starego CRM.** Kolumna „Szansa sprzedaży Etykieta” (Nowy klient,
  Upsell, Odnowienie, Projekt jednorazowy, Abonament) mapuje się na
  `opportunity_type` tylko częściowo (brak odpowiedników dla „Projekt
  jednorazowy” i „Abonament”). Do rozstrzygnięcia przy imporcie.
- **Tworzenie osób z listy HR.** `to_be_audited` wymaga istniejących osób.
  Przy trzech nowych osobach ktoś musi je najpierw utworzyć w `persons` (imię,
  e-mail, firma). Możliwe usprawnienie na później: publiczny formularz NocoDB
  dla HR albo pole tekstowe z listą, które flow zamieni na osoby.
- **Wdrożenie cal.com.** To cal.com w chmurze. W repo nie ma jego konfiguracji,
  więc typy wydarzeń, konta metodyczek i webhooki trzeba ustawić po stronie
  cal.com. Dostępność webhooków, pól rezerwacji i parametrów linku zależy od
  planu w chmurze: do sprawdzenia przed implementacją.
- **Brak osi czasu rozmów.** Trwałe notatki są w `notes` na leadzie, szansie i
  osobie; kontakty z terminem to zadania. Nie ma jednej listy „kto, kiedy i o
  czym rozmawiał" jak w dzienniku Pipedrive (świadoma decyzja, A12).
- **Rezerwacje poza cal.com.** Wpis wprost w kalendarzu nie zasili CRM; to
  świadomy koszt przejścia z odpytywania kalendarza na webhooki.
- **`audited` może się rozjechać z `assessments`.** Dopisuje je n8n przy
  tworzeniu oceny; ręczne usunięcie oceny nie cofnie wpisu.
- **Pola Button i rollupy.** Przycisk konwersji jest placeholderem (jak
  istniejące); rollupy / formuły w `offers`, `recommendations` i
  `selected_*` nie zmieniają się.

---

## Zmiany w `scripts/init-schema.py` (wejście do planu migracji)

- `TABLES`: dodać `persons`, `sale_opportunities`,
  `sale_opportunity_stage_history`, `employees`, `absences`; usunąć
  `participants`; odchudzić `leads`; dodać pola do `assessments`; zmienić
  `owner` / `assignee` (User) na relacje.
- Jedna stała dla listy etapów (`STAGES`), użyta w trzech miejscach.
- `RELATIONS`: według tabeli wyżej; usunąć stare wpisy z `participants`.
- `persons`: dodać `sales_mode` (SingleSelect, domyślnie `Standard`).
- `leads`: dodać `primary_person` (relacja z `persons`), `convert_status`,
  `convert_note`. `sale_opportunities`: dodać `stage_changed_at`. `offers`: usunąć `template_name` (link do szablonu zostaje
  bez zmian), dodać `approved_total`, przycisk „Utwórz nową wersję" i
  `version_status` / `version_note`, opcję `approved` w `status`.
- Opcje `stage` / `from_stage` / `to_stage` z jednej stałej, polskie nazwy
  według sekcji „Nazwy etapów".
- `tasks`: dodać `scheduled_for` (Date) i opcję `scheduled` w `status`; dodać
  `task_type` (SingleSelect) i usunąć z flow wszelkie
  rozpoznawanie rodzaju zadania po tytule; `meetings`: dodać `external_id`.
- `BUTTONS`: dodać „Utwórz szansę sprzedaży" na `leads` i „Generuj zadania
  audytowe" na `sale_opportunities`.
- `create_tables()` pomija istniejącą tabelę po tytule, a `init-schema.py` nie
  zmienia ani nie usuwa pól na istniejących tabelach. Pola do usunięcia
  (`leads.stage` itd., `tasks.assignee` jako `User`) i tabelę `participants`
  trzeba zdjąć osobnym krokiem albo odtworzyć bazę.
- `scripts/upgrade-links.py` korzysta z `RELATIONS`, więc obejmie nowe relacje
  bez zmian.
- Skrypty, które piszą do starych tabel i pól: `scripts/seed-extra.py`
  (m.in. `offers.template_name`),
  `scripts/import-*.py`, `init-data/generate_crm_data.py`,
  `docs/archive/fable/seed_nocodb.py`, `import_legacy_excel.py`,
  `test_cases.md`.

Gotowe odniesienie implementacyjne: `scripts/demo-schema-init.py` i
`scripts/demo-seed.py` (tabele `demo_*` z relacjami, śledzenie pól zwrotnych,
dwa przykłady B2C i B2B).
