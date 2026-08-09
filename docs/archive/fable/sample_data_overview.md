# Dane przykładowe — mapa relacji

Uruchomienie: uzupełnij `CONFIG` w `seed_nocodb.py` (URL, token, base ID, maile zespołu), potem `pip install requests && python3 seed_nocodb.py`. Skrypt sam rozwiązuje ID tabel i pól linkujących z meta API — warunek: nazwy tabel i pól linkujących zgodne ze schematem v2 (`companies`, `leads`, `participants`, `meetings`, `tasks`, `task_templates`, `projects`, `activities`, `testimonials`; pola linków: `lead`, `company`, `participant`, `project`, `template`, `selected_testimonials`). Jeśli nazwa się nie zgadza, skrypt nie wywali się — wypisze `! link field not found` z listą dostępnych pól, żebyś wiedział co poprawić.

## Dataset

```
TechFlow Sp. z o.o. ──┬── L2 Marta Kowal (B2B, audit) ──┬── P2 Jan Dąbrowski ── M3 Audyt (scheduled)
                      │                                 ├── P3 Ola Wrona
                      │                                 ├── P4 Tomasz Lis
                      │                                 └── M2 Discovery (done)
                      └── L4 Karol Wiśniewski (B2B, pending_confirmation) ── M4 Discovery (scheduled)

Baltic Logistics S.A. ── (bez leadów — firma "śpiąca" w bazie)

L1 Piotr Zieliński (B2C, draft_ready) ──┬── P1 Piotr (CEFR wypełnione)
                                        ├── M1 Discovery (done, transcript + ai_analysis, ai_accepted)
                                        ├── testimonials: T1 (case study IT) + T2 (opinia B2C)
                                        └── activities: pełny timeline "Piotr" (7 wpisów)

L3 Adam Nowicki (B2C para, new) ──┬── P5 Adam
                                  └── P6 Ewa Nowicka
```

## Co który rekord udowadnia

| Sprawdź w NocoDB | Relacja | Oczekiwany wynik |
|---|---|---|
| `companies` → TechFlow → pole `leads` | one-to-many (company→leads) | 2 leady: Marta i Karol — scenariusz "firma wraca po więcej" |
| `leads` → L2 Marta → pole `participants` | one-to-many (lead→participants) | 3 osoby; Marta NIE jest wśród nich (kupujący ≠ szkolony) |
| `leads` → L3 Adam → `participants` | one-to-many | 2 osoby (para) — wariant B2C grupowy |
| `leads` → L1 Piotr → `selected_testimonials` ORAZ `testimonials` → T1 → `used_in_leads` | **many-to-many** | link widoczny z obu stron |
| `meetings` → "Audyt — Jan Dąbrowski" → `participant` | many-to-one | dokładnie 1 uczestnik; discovery Marty bez uczestnika |
| `tasks` → task "Raport marketingowy..." → `template` | many-to-one | proweniencja taska z szablonu (W1) |
| `tasks` → "Newsletter lipcowy" | opcjonalność linku | task marketingowy BEZ leada — łącznik tylko do projektu |
| `activities` → filtr po L1, sort po `created_at` | one-to-many + timeline | 7 wpisów czyta się jak dziennik scenariusza "Piotr" |
| widok Kanban na `leads` po `stage` | — | 4 karty w 4 różnych kolumnach |
| widok Calendar na `meetings` | — | M3 i M4 w najbliższych dniach, M1/M2 w przeszłości |
| widok Calendar na `tasks` per osoba | — | taski Przemka/Doroty/Kasi rozłożone na ±4 dni |

## Uwagi

- Daty liczone względem dnia uruchomienia (`d(-4)`, `dt(2, 9)` itd.) — kalendarze od razu wyglądają sensownie, niezależnie kiedy odpalisz.
- Pola User (`owner`, `assignee`, `assigned_methodologist`) ustawiane mailem — **maile w CONFIG muszą należeć do zaproszonych członków bazy**, inaczej NocoDB odrzuci wartość. Jeśli na czas testów masz tylko jedno konto, wpisz wszędzie swój mail.
- Ponowne uruchomienie tworzy duplikaty — przed re-seedem wyczyść tabele (albo skasuj i odtwórz bazę).
- L4 celowo ma `company_match_status = pending_confirmation` + task "Confirm company match" + activity `company_match_suggested` — czyli stan dokładnie taki, jaki zostawi po sobie workflow W5. Możesz na nim przećwiczyć ręczną ścieżkę `confirmed`/`rejected` zanim W5 pójdzie na produkcję.
