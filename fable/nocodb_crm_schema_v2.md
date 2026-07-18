# CoAction — projekt bazy NocoDB (faza 1, v2)

Zmiany vs v1: dodane tabele `activities` (log zdarzeń pisany przez n8n) i `testimonials` (biblioteka referencji), pipeline po spotkaniu 1:1 (`meetings.processing_status` + `leads.offer_prep_status`), workflow W6.

Stack: PostgreSQL + NocoDB CE + n8n, self-hosted (Mikrus 4.1 PRO).
Konwencja: nazwy pól po angielsku w `snake_case` (stabilne ID dla API i n8n), etykiety wyświetlane w NocoDB mogą być po polsku. Kod i komentarze w n8n — po angielsku.

Zasada podziału odpowiedzialności:
- **NocoDB** = stan bieżący + widoki + formularze + webhooki.
- **n8n** = wszystko, co się dzieje "samo": taski cykliczne, daty kamieni milowych, powiadomienia, dedup firm.
- **Postgres** = źródło prawdy + raporty SQL, których nie da się zrobić w CE (filtrowane rollupy są płatne).

---

## Architektura tabel

```
companies ──< leads ──< meetings
    │           │  \──< participants >── meetings (audyty per osoba)
    │           │  \──< tasks
    │           │  \──< activities   (append-only, pisze TYLKO n8n)
    │           │  \──> testimonials (wybrane referencje do oferty)
    │           └────── offers (faza 2)
    └─────< participants
projects ──< tasks >── task_templates (via n8n)
```

Zasada dla `activities`: ludzie zmieniają statusy w `leads`/`meetings`/`tasks`, n8n wykonuje pracę i dopisuje wpis do logu. Nikt nie edytuje `activities` ręcznie — to timeline i ślad audytowy, nie miejsce pracy.

Jedna baza (workspace), wszystkie tabele razem — warunek działania widoków "moje taski ze wszystkich projektów".

---

## 1. `companies`

Firma jako byt trwały. Lead to pojedyncza szansa sprzedaży; firma może mieć wiele leadów w czasie (inny dział, kolejny rok).

| Pole | Typ NocoDB | Wypełnia | Uwagi |
|---|---|---|---|
| `name` | SingleLineText (display value) | człowiek / n8n | |
| `domains` | SingleLineText | n8n / człowiek | domeny e-mail rozdzielone przecinkiem, np. `acme.pl, acme.com` — klucz do dedupu |
| `nip` | SingleLineText | człowiek | opcjonalne; drugi klucz dedupu przy umowie |
| `industry` | SingleSelect | człowiek | te same opcje co w `leads.industry` |
| `size` | SingleSelect | człowiek | np. `<10`, `10-50`, `51-250`, `250+` |
| `folder_url` | URL | człowiek | odpowiednik "Folder klienta" z Excela |
| `notes` | LongText | człowiek | kontekst biznesowy, procesy komunikacyjne (z docx: sekcja "Kontekst biznesowy") |
| `leads` | Links → leads | auto | |
| `participants` | Links → participants | auto | |

**Ważne:** rekord `companies` powstaje tylko dla B2B (lub B2C, gdy klient wraca i ma sens grupowanie). Nie tworzymy firmy dla każdego gmaila.

---

## 2. `leads`

Jedna szansa sprzedaży. Kanban żyje tutaj.

| Pole | Typ NocoDB | Wypełnia | Uwagi |
|---|---|---|---|
| `lead_id` | Autonumber | auto | kontynuacja numeracji z Excela (import ustawi sekwencję od 1640+) |
| `contact_name` | SingleLineText (display) | formularz / n8n | osoba kontaktowa = kupujący (nie mylić z participant) |
| `contact_email` | Email | formularz / n8n | klucz dedupu domenowego |
| `contact_phone` | PhoneNumber | formularz / człowiek | |
| `company` | Links → companies (many-to-one) | człowiek / n8n (propozycja) | puste dla typowego B2C |
| `type` | SingleSelect: `B2C`, `B2B` | n8n / człowiek | n8n proponuje po domenie maila, człowiek weryfikuje (zgodnie z docx) |
| `owner` | User | n8n (default: Przemek) | handlowiec |
| `source` | SingleSelect | formularz / człowiek | `google`, `polecenie`, `linkedin`, `powrot_klienta`, `inne` |
| `contact_channel` | SingleSelect | n8n / człowiek | `bookings`, `formularz`, `email`, `telefon` |
| `qualification` | SingleSelect: `unqualified`, `MQL`, `SQL` | człowiek | świadoma decyzja, nie automat (docx pkt 5) |
| `disqualify_reason` | SingleSelect + `disqualify_note` LongText | człowiek | |
| `stage` | SingleSelect | człowiek (drag na kanbanie) | patrz lista startowa niżej; edycja opcji = zero migracji |
| `state` | SingleSelect: `open`, `won`, `lost`, `archived` | człowiek / n8n | n8n ustawia `won` przy stage=`contract_signed` |
| `loss_reason` | SingleSelect + `loss_note` | człowiek | n8n tworzy task "uzupełnij powód", jeśli puste przy `lost` |
| `value` | Currency (PLN) | człowiek | wartość szansy |
| `label` | SingleSelect | człowiek | odpowiednik "Etykieta" z Excela (np. `hot`, `oferta_specjalna`) |
| `industry` | SingleSelect | człowiek | dla B2C bez firmy (np. "Software Development" z leada 1639) |
| `notes` | LongText | człowiek | notatki bieżące; notatki ze spotkań idą do `meetings.notes` |
| `company_match_status` | SingleSelect: `none`, `pending_confirmation`, `confirmed`, `rejected` | n8n / człowiek | patrz workflow dedupu niżej |
| `offer_prep_status` | SingleSelect: `none`, `waiting_goals`, `goals_provided`, `testimonials_provided`, `draft_ready` | człowiek + n8n | pipeline produkcji oferty (workflow W6); celowo osobno od `stage`, żeby kanban sprzedażowy pozostał czysty |
| `training_goals` | LongText | metodyk | cele szkoleniowe zatwierdzone do oferty |
| `selected_testimonials` | Links → testimonials | analityk | referencje dobrane do tej oferty |
| **Kamienie milowe (wypełnia wyłącznie n8n):** | | | |
| `created_at` | CreatedTime | auto | = "Data wpłynięcia" |
| `offer_sent_at` | Date | n8n | przy wejściu w stage `offer_sent` |
| `contract_sent_at` | Date | n8n | |
| `closed_at` | Date | n8n | przy `won` / `lost` / `archived` |
| **Linki:** `meetings`, `participants`, `tasks` | Links | auto | |

**Startowa lista `stage`** (do edycji bez bólu, jak ustaliliśmy):
`new` → `discovery_scheduled` → `discovery_done` → `audit` → `recommendation` → `offer_sent` → `offer_discussed` → `contract_sent` → `contract_signed` | `lost` | `archived`

B2C w praktyce przeskakuje: `new` → `discovery_done` → `offer_sent` (DEMO) → `contract_signed`. Ten sam select obsługuje oba flow.

---

## 3. `participants`

Osoba faktycznie szkolona. Dla B2C "kupuję dla siebie" — lead ORAZ participant to ta sama osoba fizyczna, ale dwa rekordy (participant powstaje przy audycie/starcie). Dla par/grup — wiele participants na jeden lead. Dla B2B — CEO jest w `leads`, pracownicy tutaj.

| Pole | Typ NocoDB | Wypełnia | Uwagi |
|---|---|---|---|
| `full_name` | SingleLineText (display) | człowiek | |
| `position` | SingleLineText | człowiek | np. "Senior Frontend Developer" — idzie wprost na slajd 1 oferty |
| `linkedin_url` | URL | człowiek | jest w notatkach z rozmów |
| `lead` | Links → leads (many-to-one) | człowiek | |
| `company` | Links → companies | człowiek / n8n | |
| `email` | Email | człowiek | do formularzy przed-audytowych (faza 2) |
| **Oceny CEFR (z audytu, wypełnia metodyk):** | | | struktura 1:1 ze slajdem 3 ofert PPTX |
| `cefr_overall` | SingleLineText | metodyk | np. `B2.6` (skala z częściami dziesiętnymi — text, nie number) |
| `cefr_range` | SingleLineText | metodyk | zakres języka |
| `cefr_accuracy` | SingleLineText | metodyk | poprawność |
| `cefr_fluency` | SingleLineText | metodyk | płynność |
| `cefr_communication` | SingleLineText | metodyk | komunikatywność |
| `audit_notes` | LongText | metodyk | mocne strony, luki, obserwacje |
| `needs_summary` | LongText | metodyk / AI-draft (faza 2) | sytuacje komunikacyjne, cele — źródło sekcji "Potrzeba szkoleniowa" w ofercie |
| `assigned_methodologist` | User | człowiek | Dorota (B2B) / Aleksandra (1:1) |
| `meetings` | Links → meetings | auto | audyty tej osoby |

---

## 4. `meetings`

Tylko prawdziwe spotkania. Kalendarz spotkań = widok Calendar na tej tabeli.

| Pole | Typ NocoDB | Wypełnia | Uwagi |
|---|---|---|---|
| `title` | SingleLineText (display) | n8n / człowiek | np. "Audyt — Jan Kowalski" |
| `type` | SingleSelect | człowiek / n8n | `discovery`, `demo`, `audit`, `needs_analysis`, `offer_discussion`, `other` |
| `starts_at` | DateTime | n8n (Bookings) / człowiek | |
| `ends_at` | DateTime | opcjonalnie | Calendar view obsłuży zakres |
| `lead` | Links → leads | człowiek / n8n | |
| `participant` | Links → participants | człowiek | wypełniane dla audytów |
| `owner` | User | człowiek / n8n | kto prowadzi |
| `status` | SingleSelect: `scheduled`, `done`, `no_show`, `cancelled` | człowiek | |
| `notes` | LongText | człowiek | notatka typu "Rozmowa wprowadzająca" — dokładnie to, co dziś jest w Wordach |
| `transcript` | LongText | człowiek | wklejona transkrypcja (LongText w NocoDB mieści ją bez problemu; alternatywnie `transcript_url`, jeśli transkrypcje zostają w plikach) |
| `ai_analysis` | LongText | **n8n** | szkic analizy z LLM (OpenRouter); człowiek nie edytuje — poprawki wpisuje do `notes`/`outcome`, a szkic akceptuje lub odrzuca statusem |
| `processing_status` | SingleSelect: `none`, `analysis_pending`, `ai_draft_ready`, `ai_accepted`, `ai_rejected` | człowiek + n8n | maszyna stanów W6a; dotyczy TEGO spotkania — dalsze etapy (cele, referencje) żyją na leadzie w `offer_prep_status` |
| `outcome` | LongText | człowiek | decyzje po spotkaniu |

---

## 5. `tasks` — JEDNA tabela dla całej firmy

Warunek działania ficzera nr 1. Task = "co mamy zrobić" (meetings = "co się wydarzyło").

| Pole | Typ NocoDB | Wypełnia | Uwagi |
|---|---|---|---|
| `title` | SingleLineText (display) | człowiek / n8n | |
| `assignee` | User | człowiek / n8n | podstawa widoków per osoba |
| `due_date` | Date | człowiek / n8n | podstawa widoku Calendar |
| `status` | SingleSelect: `todo`, `in_progress`, `done`, `cancelled` | człowiek | |
| `priority` | SingleSelect: `low`, `normal`, `high` | człowiek | |
| `project` | Links → projects | człowiek / n8n | |
| `lead` | Links → leads | n8n / człowiek | puste dla tasków marketingowych |
| `description` | LongText | człowiek / n8n | |
| `template` | Links → task_templates | n8n | śladowość: skąd task pochodzi |
| `created_by_flow` | SingleLineText | n8n | nazwa workflow n8n (debug) |

## 6. `task_templates`

Czytane wyłącznie przez cron w n8n (workflows z CRON triggerem w NocoDB są płatne — stąd n8n).

| Pole | Typ | Uwagi |
|---|---|---|
| `title` | SingleLineText | może zawierać placeholdery, np. `{{month}}` |
| `assignee` | User | |
| `project` | Links → projects | |
| `rrule` | SingleLineText | np. `FREQ=WEEKLY;BYDAY=MO` — standard RRULE, n8n parsuje |
| `due_offset_days` | Number | due_date = data utworzenia + offset |
| `description` | LongText | |
| `active` | Checkbox | wyłączanie bez kasowania |

## 7. `projects`

Prosty słownik: `name`, `team` (SingleSelect: `marketing`, `sales`, `ops`), `active`. Startowo: Marketing, Sprzedaż, Wewnętrzne.

## 8. `activities` — log zdarzeń (append-only, pisze wyłącznie n8n)

Każdy workflow n8n kończy się node'em "log activity". Timeline leada = widok Grid z filtrem po leadzie, sort malejąco po dacie. Ludzie tu tylko czytają.

| Pole | Typ NocoDB | Uwagi |
|---|---|---|
| `summary` | SingleLineText (display) | czytelne dla człowieka, np. "AI analysis ready for meeting: Discovery — Piotr" |
| `type` | SingleSelect | `lead_created`, `stage_changed`, `task_created`, `task_completed`, `meeting_created`, `transcript_added`, `ai_analysis_done`, `ai_accepted`, `goals_provided`, `testimonials_provided`, `offer_draft_ready`, `company_match_suggested`, `notification_sent`, `automation_error` |
| `lead` | Links → leads | prawie zawsze wypełnione |
| `meeting` | Links → meetings | opcjonalnie |
| `task` | Links → tasks | opcjonalnie |
| `triggered_by` | SingleLineText | e-mail osoby, której akcja uruchomiła flow, albo `system` (cron) |
| `flow` | SingleLineText | nazwa workflow n8n (np. `W6a`) — debug w 5 sekund |
| `payload` | LongText | JSON ze szczegółami (stara/nowa wartość, model LLM, koszt tokenów itp.) |
| `created_at` | CreatedTime | |

Dwa zyski poza timeline'em: (1) debugging automatów — gdy coś nie zadziała, `automation_error` z payloadem ląduje w bazie zamiast ginąć w logach n8n; (2) surowiec pod raporty SQL (ile trwa krok "verify AI" per metodyk itd.).

## 9. `testimonials` — biblioteka referencji

Analityk nie wkleja referencji do oferty, tylko linkuje z biblioteki — dzięki temu ta sama referencja jest reużywalna i wiadomo, gdzie była użyta.

| Pole | Typ NocoDB | Uwagi |
|---|---|---|
| `title` | SingleLineText (display) | |
| `client_name` | SingleLineText | |
| `industry` | SingleSelect | te same opcje co w leads — ułatwia dobór "referencja z branży klienta" |
| `type` | SingleSelect | `testimonial`, `case_study` |
| `content` | LongText | |
| `variant` | MultiSelect | `business_english`, `english_for_it`, `english_business_skills` — do jakiego wariantu szkolenia pasuje |
| `active` | Checkbox | |
| `used_in_leads` | Links → leads | odwrotność `selected_testimonials` |

---

## Widoki (mapowanie na wymagane ficzery)

| Ficzer | Realizacja |
|---|---|
| Lista "moje taski ze wszystkich projektów" | `tasks` → Grid "Taski Przemka" (filtr `assignee = Przemek`, `status != done`), analogicznie per osoba (5 widoków) |
| Kalendarz moich tasków | `tasks` → Calendar po `due_date`, per osoba |
| Powtarzalne taski | `task_templates` + n8n cron (workflow W1) |
| Kanban po etapie | `leads` → Kanban po `stage`, filtr `state = open`; drugi kanban "Zamknięte" bez filtra dla przeglądu |
| Dodaj lead ręcznie | `leads` → Form view (pola: contact_name, email, phone, source, type, notes); reszta domyślna/n8n |
| Kalendarz spotkań (bonus) | `meetings` → Calendar po `starts_at` |
| Timeline leada ("co się działo?") | `activities` → Grid, grupowanie po `lead`, sort `created_at` malejąco; najwygodniej jednak czytać z poziomu rekordu leada — podlinkowane activities widać w expanded record |
| Kolejka weryfikacji AI | `meetings` → Grid, filtr `processing_status = ai_draft_ready` |
| Produkcja ofert w toku | `leads` → Kanban po `offer_prep_status`, filtr `state = open` |

Widoki per osoba ustaw jako **Locked** (żeby nikt przypadkiem nie zmienił filtra) albo Personal.

---

## Workflowy n8n (faza 1)

**W1 — Recurring tasks.** Cron (codziennie 06:00) → pobierz `task_templates` gdzie `active=true` → parsuj `rrule` → jeśli dziś pasuje: POST do `tasks`. Idempotencja: przed insertem sprawdź, czy task z tym template i dzisiejszą datą już istnieje.

**W2 — Stage change.** Webhook NocoDB (`leads` on update, pole `stage`) → switch po nowej wartości → ustaw kamień milowy (`offer_sent_at` itd.) → przy `contract_signed`: `state=won`, `closed_at` → przy `lost` bez `loss_reason`: utwórz task "Uzupełnij powód utraty" dla ownera → powiadomienie (mail/Slack) do ownera.

**W3 — Task assigned notification.** Webhook (`tasks` on create/update `assignee`) → mail/Slack do assignee. To łata największą lukę względem Asany (brak powiadomień w NocoDB CE).

**W4 — New lead intake.** Webhook z formularza NocoDB / Bookings → normalizacja danych → utwórz lead → task "Pierwszy kontakt / discovery" dla Przemka (docx, etap 1).

**W5 — Company dedup po domenie (Twój wymóg).** Trigger: nowy lead z `contact_email`.
1. Wytnij domenę z maila.
2. **Odfiltruj domeny publiczne** (gmail.com, wp.pl, o2.pl, onet.pl, interia.pl, icloud.com, outlook.com, proton.me...) — bez tej listy każdy B2C z gmailem "dopasuje się" do tej samej pseudo-firmy. Lista jako zmienna w n8n lub mała tabela `public_domains`.
3. Szukaj domeny w `companies.domains`.
4. **Trafienie** → podlinkuj proponowaną firmę, ustaw `company_match_status = pending_confirmation`, dodaj komentarz do rekordu przez API: *"Found existing company '<name>' based on email domain <domain>. Please confirm this is the same company."* + powiadom ownera (W3-style). Człowiek zmienia status na `confirmed` (zostaje link) lub `rejected` (n8n odpina link).
5. **Brak trafienia + domena firmowa** → status `none`; opcjonalnie task "Załóż rekord firmy" przy kwalifikacji SQL/B2B.

Dlaczego status jako pole, a nie sam komentarz: komentarze w CE nie filtrują widoków — pole daje widok "Do potwierdzenia dopasowania" i twardy stan dla n8n.

**W6 — pipeline po spotkaniu (scenariusz "Piotr").** Dwa webhooki:

*W6a — analiza AI (zasięg: spotkanie).* Webhook `meetings` on update `processing_status`:
- `analysis_pending` → pobierz `transcript` → OpenRouter (LLM) → zapisz wynik do `ai_analysis` → `processing_status = ai_draft_ready` → task "Verify AI analysis" dla ownera spotkania → log `ai_analysis_done` (payload: model, tokeny, koszt). Bezpiecznik: jeśli `transcript` pusty — nie wołaj LLM, tylko task "Wklej transkrypcję" i log błędu.
- `ai_accepted` → zamknij task weryfikacji → ustaw na leadzie `offer_prep_status = waiting_goals` → task "Określ cele szkoleniowe" dla metodyka (routing: B2B → Dorota, B2C → Aleksandra, wg pola `type` leada) → log `ai_accepted`.
- `ai_rejected` → task "Popraw notatki i uruchom analizę ponownie" dla ownera (człowiek edytuje `notes`, cofa status na `analysis_pending`).

*W6b — produkcja oferty (zasięg: lead).* Webhook `leads` on update `offer_prep_status`:
- `goals_provided` (metodyk wpisał `training_goals` i zmienił status) → zamknij task celów → task "Dobierz referencje" dla analityka → log.
- `testimonials_provided` (analityk podlinkował `selected_testimonials`) → zamknij task referencji → task "Szkic oferty gotowy — złóż ofertę" dla Przemka → `offer_prep_status = draft_ready` → log `offer_draft_ready`. Bezpiecznik: jeśli `selected_testimonials` puste przy tym statusie — komentarz "No testimonials linked, please add at least one" zamiast przejścia dalej.

**Reguła logowania:** każdy workflow (W1–W6) kończy się node'em "create activity". Konwencja: `flow` = ID workflow, `payload` = JSON z wartościami przed/po. Błędy każdego workflow łapie error-branch → activity `automation_error` + powiadomienie do admina.

---

## Import z Excela (twarde cięcie)

1. Daty seryjne (46149 → 2026-05-12): konwersja `date = 1899-12-30 + N dni`; godzina = ułamek doby.
2. Mapowanie kolumn: `Etap`/`Stan` → normalizacja do opcji selectów; 12 kolumn dat → `created_at` + kamienie milowe + rekordy `meetings` (Data DEMO, Data badania potrzeb, Data omówienia oferty → meetings z `status=done`).
3. `Spr. ID` z Excela → zachowaj w polu `legacy_id` (dodam do `leads`), żeby dało się wrócić do źródła przez pierwsze miesiące.
4. Skrypt importu napiszę osobno (Python, openpyxl → API NocoDB) — po zaakceptowaniu schematu.

## Świadomie odłożone do fazy 2

`offers` (historia ofert + generowanie PPTX/www z pól `participants`), formularze przed-audytowe dla uczestników, AI-draft `needs_summary` z transkrypcji, dashboard SQL na Postgresie (czas new→won, konwersja per source).
