# Katalog przypadków testowych — CoAction CRM

Legenda kolumny "Tryb": **AUTO** = w pełni deterministyczny, zaimplementowany w runnerze; **SEMI** = zawiera wywołanie LLM — runner asertuje strukturę wyniku, nie treść; **PROC** = proceduralny (weryfikacja przez `--dry-run` importera albo ręczne wykonanie w n8n).

## W0 — taski cykliczne

| ID | Scenariusz | Oczekiwany wynik | Tryb |
|---|---|---|---|
| W0-01 | szablon `FREQ=DAILY`, active | task utworzony z `created_by_flow=W0`, due = dziś + offset | AUTO* |
| W0-02 | `FREQ=WEEKLY;BYDAY=<dzisiejszy>` | task utworzony | AUTO* |
| W0-03 | `FREQ=WEEKLY;BYDAY=<inny dzień>` | brak taska | AUTO* |
| W0-04 | `FREQ=MONTHLY;BYMONTHDAY=<dziś>` | task utworzony | AUTO* |
| W0-05 | drugi run tego samego dnia | brak duplikatu (guard idempotencji) | AUTO* |
| W0-06 | szablon `active=false` | brak taska | AUTO* |
| W0-07 | `{{month}}` w tytule | podstawiony `YYYY-MM` | AUTO* |
| W0-08 | uszkodzony rrule (`FREQ=FOO`) | szablon pominięty, brak wywałki, inne szablony przetworzone | AUTO* |
| W0-09 | task z szablonu → activity `task_created` z `flow=W0` | wpis w activities | AUTO* |

*W0 ma trigger cron — kopia testowa W0-TEST dostaje dodatkowy węzeł Webhook (`test-w0-run`), którym runner odpala przebieg na żądanie (instrukcja w README).

## W2 — zmiana etapu leada

| ID | Scenariusz | Oczekiwany wynik | Tryb |
|---|---|---|---|
| W2-01 | update `stage: new → offer_sent` | `offer_sent_at = dziś`, activity `stage_changed` podlinkowana do leada | AUTO |
| W2-02 | `→ contract_signed` | `state=won`, `closed_at=dziś` | AUTO |
| W2-03 | `→ lost` bez `loss_reason` | task "Fill in loss reason" (priority high, assignee=owner) | AUTO |
| W2-04 | `→ lost` z `loss_reason` | brak taska, `state=lost`, `closed_at` ustawione | AUTO |
| W2-05 | update rekordu BEZ zmiany stage (edycja notatki) | zero akcji — guard | AUTO |
| W2-06 | payload bez `previous_rows` (checkbox wyłączony) | zero akcji, brak wywałki | AUTO |
| W2-07 | `→ contract_sent` | `contract_sent_at = dziś` | AUTO |
| W2-08 | `→ archived` | `state=archived`, `closed_at` | AUTO |
| W2-09 | owner jako tablica vs obiekt w payloadzie | mail idzie do właściwego adresu (oba warianty) | AUTO |

## W3 — powiadomienia o taskach

| ID | Scenariusz | Oczekiwany wynik | Tryb |
|---|---|---|---|
| W3-01 | insert taska z assignee | activity `notification_sent` (mail w MailHog) | AUTO |
| W3-02 | update: zmiana assignee A→B | powiadomienie do B | AUTO |
| W3-03 | update bez zmiany assignee | zero akcji | AUTO |
| W3-04 | task bez assignee | zero akcji, brak błędu | AUTO |

## W4 v2 — intake + kaskada dopasowań

| ID | Scenariusz | Oczekiwany wynik | Tryb |
|---|---|---|---|
| W4-01 | Tally: nowy mail, brak dopasowań, krótka wiadomość | Tier5: lead + task "Zaklasyfikuj", `enquiry_no=1`, activity `tier5` | AUTO |
| W4-02 | mail = otwarty lead | Tier1_open: BRAK nowego leada, task "Klient napisał ponownie" dla ownera, activity z treścią | AUTO |
| W4-03 | mail = zamknięty lead (won) | Tier1_closed: nowy lead, `enquiry_no=2`, `source=powrot_klienta`, firma odziedziczona ze starego | AUTO |
| W4-04 | mail = 2 zamknięte leady | `enquiry_no=3`, referencja do najnowszego | AUTO |
| W4-05 | inne dane, ta sama osoba: "Michał Kowalski" vs istniejący "Michal Kowalski" (diakrytyki) | Tier3: nowy lead `duplicate_check=pending_confirmation`, link `possible_duplicate`, komentarz, task | AUTO |
| W4-06 | zgodny telefon w innym formacie (`+48 600-100-200` vs `600100200`) | Tier3 match | AUTO |
| W4-07 | imię ≤4 znaki po foldzie ("Jan") | brak Tier3, spada niżej | AUTO |
| W4-08 | domena publiczna (gmail) | propozycja `type=B2C` | AUTO |
| W4-09 | domena firmowa nieznana | `type=B2B`, po insercie W5 nie sugeruje (brak firmy) | AUTO |
| W4-10 | CF7: payload flat JSON | poprawne mapowanie pól adaptera | AUTO |
| W4-11 | Bookings: payload z booking | meeting `scheduled` utworzony i podlinkowany do leada z kaskady (każdy tier) | AUTO |
| W4-12 | Bookings + mail otwartego leada | meeting podpięty do ISTNIEJĄCEGO leada, brak nowego | AUTO |
| W4-13 | pusty e-mail w formularzu | `email_query` nie matchuje niczego, flow dochodzi do końca | AUTO |
| W4-14 | długa wiadomość z nazwą istniejącej firmy w treści | Tier4: LLM ekstrahuje → firma podlinkowana, `company_match_status=pending`, task "(AI, do potwierdzenia)", kryteria w payload activity | SEMI |
| W4-15 | długa wiadomość "szukam dla naszego 8-os. zespołu" z gmaila | `type_signal=B2B` nadpisuje B2C | SEMI |
| W4-16 | długa wiadomość bez żadnych tropów | LLM-miss → fallback do Tier5 | SEMI |
| W4-17 | LLM zwraca niepoprawny JSON | graceful parse → Tier5, brak wywałki | SEMI |

## W5 — dedup firm po domenie

| ID | Scenariusz | Oczekiwany wynik | Tryb |
|---|---|---|---|
| W5-01 | insert leada z mailem w domenie istniejącej firmy | link lead→firma, `pending_confirmation`, komentarz, activity | AUTO |
| W5-02 | domena publiczna | zero akcji | AUTO |
| W5-03 | domena firmowa bez firmy w bazie | zero akcji (cicho) | AUTO |
| W5-04 | firma z listą domen `a.pl, b.pl` — mail z `b.pl` | match | AUTO |
| W5-05 | pułapka substring: firma `techflow.pl`, mail z `flow.pl` | BRAK matchu (exact-token, nie contains) | AUTO |
| W5-06 | lead już podlinkowany do firmy (utworzony przez W4 tier1_closed) | zero akcji — guard `if (row.company)` | AUTO |

## W6a — pipeline AI po spotkaniu

| ID | Scenariusz | Oczekiwany wynik | Tryb |
|---|---|---|---|
| W6a-01 | `→ analysis_pending`, transcript >50 znaków | `ai_analysis` niepuste, `processing_status=ai_draft_ready`, task "Verify AI analysis" (marker `meeting:{id}` w opisie), activity z modelem/usage | SEMI |
| W6a-02 | `→ analysis_pending`, transcript pusty/krótki | task "Paste transcript", activity `automation_error`, LLM NIE wywołany | AUTO |
| W6a-03 | `→ ai_accepted`, lead B2B | task "Define training goals" → Dorota, `offer_prep_status=waiting_goals`, task weryfikacji zamknięty | AUTO |
| W6a-04 | `→ ai_accepted`, lead B2C | task → Aleksandra | AUTO |
| W6a-05 | `→ ai_rejected` | task "Fix notes & rerun" dla ownera | AUTO |
| W6a-06 | update spotkania bez zmiany `processing_status` | zero akcji, zero kosztów LLM | AUTO |
| W6a-07 | dwa otwarte taski weryfikacji tego samego spotkania | oba zamknięte (bulk PATCH) | AUTO |

## W6b — produkcja oferty

| ID | Scenariusz | Oczekiwany wynik | Tryb |
|---|---|---|---|
| W6b-01 | `→ goals_provided` | task celów zamknięty, task "Select testimonials" → analityk | AUTO |
| W6b-02 | `→ testimonials_provided`, ≥1 referencja podlinkowana | task referencji zamknięty, task "assemble the offer" → Przemek, `offer_prep_status=draft_ready` | AUTO |
| W6b-03 | `→ testimonials_provided`, 0 referencji | komentarz "No testimonials linked", activity `automation_error`, status NIE przechodzi na draft_ready | AUTO |
| W6b-04 | update bez zmiany `offer_prep_status` | zero akcji | AUTO |
| W6b-05 | `→ waiting_goals` (stan przejściowy z W6a) | zero akcji W6b (nie jego branch) | AUTO |

## Importer legacy (Excel)

| ID | Scenariusz | Oczekiwany wynik | Tryb |
|---|---|---|---|
| IMP-01 | data jako datetime / liczba seryjna / pusta | poprawny ISO / poprawny ISO / None | PROC (dry-run) |
| IMP-02 | `Godzina wpłynięcia` jako time i jako ułamek doby | poprawny `received_at` | PROC |
| IMP-03 | `Etap` spoza STAGE_MAP | raport UNMAPPED, pole pominięte, wiersz zaimportowany | PROC |
| IMP-04 | `Stan=zamknięta` + data podpisania / + powód utraty / + nic | `won` / `lost` / `archived` | PROC |
| IMP-05 | 3 wiersze z tym samym mailem | `enquiry_no` 1,2,3 wg daty wpłynięcia | PROC |
| IMP-06 | re-run po częściowym imporcie | pominięte istniejące `legacy_id`, zero duplikatów | PROC |
| IMP-07 | B2B z `Osoba kontaktowa` | `contact_name` = osoba, firma z `Organizacja` | PROC |
| IMP-08 | `--dry-run` | zero zapisów do bazy (licznik rekordów bez zmian) | PROC |
| IMP-09 | 2 wiersze z tą samą `Organizacja` | jedna firma, dwa leady podlinkowane | PROC |
| IMP-10 | pełny surowy wiersz w payload activity | JSON odtwarza wszystkie niepuste kolumny Excela | PROC |

## Przekrojowe

| ID | Scenariusz | Oczekiwany wynik | Tryb |
|---|---|---|---|
| X-01 | każda auto-akcja W0, W2–W6 | wpis w `activities` z wypełnionym `flow` | AUTO (asercja w każdym teście) |
| X-02 | W4 tier1_closed → insert leada odpala W5 | brak podwójnej sugestii firmy (guard W5-06) | AUTO |
| X-03 | wszystkie webhooki z wyłączonym "include previous record" | żaden workflow nie wykonuje akcji (guardy) — test dymny konfiguracji | AUTO |
