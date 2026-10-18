# CoAction CRM — plan migracji do schematu v4

Specyfikacja docelowa: [nocodb_crm_schema_v4.md](nocodb_crm_schema_v4.md).
Ten dokument mówi, **w jakiej kolejności** ją wdrażamy i **jak sprawdzamy każdy etap**.
Założenia użytkownika: dane na UAT są jednorazowe, liczy się działająca całość,
a każdy etap ma się kończyć czymś, co da się obejrzeć i przetestować.

Status: **propozycja do akceptacji**. Nic w `scripts/init-schema.py` ani we flow
nie jest jeszcze zmienione.

---

## Decyzje potrzebne przed etapem 0

Poniżej wartości domyślne, które przyjąłem; każda blokuje konkretny etap, więc
najlepiej rozstrzygnąć je z góry.

| # | Decyzja | Domyślnie | Blokuje |
|---|---|---|---|
| D1 | Środowisko budowy: **świeża baza na instancji testowej (staging)**, nie edycja obecnej bazy UAT w miejscu | tak, patrz „Strategia" | wszystko |
| D2 | Lista etapów `stage` i ich nazwy (A1): polskie nazwy z mapowania w specyfikacji czy etapy z Excela klientki | mapowanie ze specyfikacji | etap 1 |
| D3 | `owner` / `assignee` jako linki do `employees` zamiast pól `User` (A6) | tak | etap 1 |
| D4 | Wersje ofert: kopiowanie rekomendacji flowem czy przenoszenie (A14) | kopiowanie | etap 4 |
| D5 | Stare flow z zaszytymi ID przepinamy na konwencję „Get one base" (`.ai/rules/nocodb.md` §3a) przy okazji zmiany ID | tak, dla flow, które i tak edytujemy | etapy 1–4 |
| D6 | Zadania tworzone dziś przez istniejące flow: które zostają (Dodatek A) | wg propozycji w Dodatku A | etapy 1–4 |

---

## Strategia

`scripts/init-schema.py` tylko **tworzy**: pomija istniejące tabele i pola,
nigdy ich nie zmienia ani nie usuwa (nagłówek skryptu, „CZEGO TEN SKRYPT NIE
ROBI"). Konsekwencje dla v4:

- Zmiana istniejącej tabeli `leads` w miejscu (usunięcie `stage`, `deal_value`…)
  i usunięcie `participants` wymagałyby ręcznej pracy w UI i naruszyłyby flow.
- Dlatego **budujemy v4 od zera, w etapach, na pustej bazie** na instancji
  testowej. Obecny UAT działa nietknięty, aż do przełączenia w etapie 6. Skoro
  dane są jednorazowe, przełączenie to ponowne odtworzenie bazy od zera.
- Każda tabela powstaje **raz, ze wszystkimi polami zwykłymi** w etapie, w
  którym pierwszy raz jest potrzebna. Późniejsze etapy dokładają do niej tylko
  **relacje** (skrypt tworzy je idempotentnie po tytule pola) i **przyciski**.
  Pola zwykłe dodane do istniejącej tabeli skrypt by pominął.
- Do skryptu dochodzi opcja `--stage N` (nowy kod): tworzy tylko tabele,
  relacje i przyciski przypisane do etapu N. Uruchomiona kolejno dla etapów 1,
  2, 3… daje bazę rosnącą krok po kroku, a rozjazd wychodzi od razu.

Po każdym etapie: `make dump-crm-schema` (nowe ID do `schema_map.json`),
import i aktywacja tylko tych flow, które należą do etapu, a następnie test
akceptacyjny. Flow z późniejszych etapów zostają nieaktywne.

**Rollback etapu:** usuwamy tabele etapu w UI (relacje najpierw) i dezaktywujemy
jego flow. Wcześniejsze etapy są nietknięte, bo etapy tylko dokładają.

---

## Dane testowe (seedy)

Dane testowe wgrywamy skryptem wzorowanym na `scripts/demo-seed.py`
(proponowana nazwa `scripts/seed-test-data.py`, target `make seed-test-data`).
Zasady, przejęte z `demo-seed.py`:

- tworzenie rekordów i linków przez NocoDB API (`rec()` i `lnk()`, id pól
  relacji znajdowane po tytule), z `--dry-run` drukującym plan,
- daty względne od dnia uruchomienia, żeby widoki „Utknięte" i „Moje zadania"
  zawsze miały co pokazać,
- nie dotyka żadnych tabel poza tabelami CRM v4, a pola `User` (jeśli zostają)
  zostawia puste,
- błąd pojedynczego rekordu lub linku nie przerywa seedowania; na końcu
  podsumowanie z liczbą błędów.

Różnice względem `demo-seed.py`, bo seedujemy etapami:

- Skrypt ma `--stage N` i funkcję seedującą na etap (`seed_stage1`…`seed_stage4`).
  Każdy etap seeduje tylko tabele, które już istnieją.
- Etapy są **powtarzalne**: funkcja sprawdza rekord kontrolny etapu (np. osobę o
  znanym e-mailu) i pomija etap, jeśli już był seedowany. Etap N znajduje rekordy
  wcześniejszych etapów po stabilnych kluczach (e-mail osoby, nazwa szansy),
  zamiast zakładać pustą bazę jak `demo-seed.py`.

Zestaw danych (jeden spójny, rosnący z etapami):

| Etap | Dane |
|---|---|
| 1 | 4 pracowników (handlowiec, metodyczka B2B, metodyczka B2C, finanse); urlop handlowca z zastępczynią w czasie dzisiejszych terminów; firma Acme; osoby Anna, Marek, Joanna, Tomasz, Ewa, Piotr, Karol oraz księgowa z `sales_mode` = Tylko spotkania; lead Anny i lead Acme (z trzema osobami i `primary_person`) zamienione na szanse z historią etapów; świeży lead niezakwalifikowany (do widoku „Leady do zakwalifikowania"); szansa przegrana z powodem; szansa utknięta (`stage_changed_at` sprzed 20 dni); zadania `scheduled` na jutro, `todo` na dziś i `done` |
| 2 | spotkania discovery i demo dla Anny i dla Acme (Marek), spotkanie księgowej bez szansy, spotkanie bez typu (do widoku kontrolnego) |
| 3 | trzy audyty Acme (po jednym uczestniku), audyt Anny, oceny, `to_be_audited` / `audited` / `participants` (Ewa i Piotr zapisani, Karol po audycie), `audit_scope`, trzy zadania `audit_prep` |
| 4 | rekomendacje, oferta Anny (`approved`, `accepted`), oferta Acme v1 (3 osoby) i v2 (2 osoby) z `approved_total` i `deal_value` |

Katalogi etapu 4 (cennik, pakiety, referencje, szablony) wgrywają istniejące
skrypty `import-pricing`, `import-packages`, `import-testimonials`; seed
etapu 4 uruchamiamy po nich i wskazuje na ich wiersze.

Seed jest jednocześnie danymi dla testów akceptacyjnych S1–S5 i dla widoków
(każdy widok z listy w specyfikacji ma przynajmniej jeden rekord, który go
wypełnia). Dla S1 i S2 testy najpierw przechodzą scenariusz flow od początku;
seed służy do pozostałych widoków i do odbioru.

---

## Etap 0 — przygotowanie (bez zmian w środowisku)

Cel: kod i testy gotowe, żeby etapy 1–4 były wyłącznie wdrażaniem.

- `scripts/init-schema.py`: nowe `TABLES` i `RELATIONS` według v4; jedna stała
  `STAGES`; przypisanie każdej tabeli, relacji i przycisku do etapu; opcja
  `--stage N`. Usunięcie `participants` i pól przeniesionych (lista w v4,
  „Zmiany w `scripts/init-schema.py`").
- `scripts/upgrade-links.py` czyta `RELATIONS`, więc obejmie nowe relacje bez
  zmian; dodajemy tylko filtr po etapie.
- Dane testowe: nowy skrypt seedujący według sekcji „Dane testowe (seedy)"
  niżej, wzorowany na `scripts/demo-seed.py`.
- Test Runner (`test_workflows.py`, `test_cases.md`): przypadki akceptacyjne
  etapów jako scenariusze (S1–S5, niżej) i zawartość `conftest.py`.
- Skill `n8n-flow` i reguły `.ai/rules/*`: zaktualizowane o `persons`,
  `sale_opportunities`, zasadę „tytuł jest dla zespołu" i politykę zadań.

**Wyjście:** `python3 scripts/init-schema.py --dry-run --stage N` poprawnie
wypisuje plan dla każdego N; testy kompilują się (jeszcze bez instancji).

---

## Etap 1 — ludzie, leady, szanse i zadania

**Tabele:** `employees`, `absences`, `companies`, `persons`, `leads`,
`sale_opportunities`, `sale_opportunity_stage_history`, `tasks`,
`task_templates`, `projects`, `activities`.

**Pola i relacje:** komplet pól zwykłych tych tabel według v4 (m.in.
`persons.sales_mode`, `leads.primary_person`, `sale_opportunities.stage_changed_at`,
`tasks.scheduled_for`, `tasks.task_type`, status `scheduled`); relacje między
nimi; przycisk „Utwórz szansę sprzedaży" z `convert_status` / `convert_note`.
Linki do `meetings`, `assessments`, `offers`, `recommendations` w `tasks` dochodzą
razem z tymi tabelami w późniejszych etapach (relacje dokładamy po tytule pola).

**Flow:**

| Flow | Zmiana |
|---|---|
| W4v2 / W4v3 intake | dopasowanie / utworzenie `persons` po e-mailu, `leads`, `primary_person`, zadanie `qualify_lead`, pominięcie `sales_mode` = Tylko spotkania |
| NOWY: konwersja | przycisk na leadzie → `sale_opportunities`, pierwszy wiersz historii; idempotentna |
| W2 | zmiana etapu na `sale_opportunities`: historia, `stage_changed_at`, zadania z tabeli przejść (bez etapu `audit` i `recommendation`, dochodzą w kolejnych etapach) |
| NOWY: wyznaczanie odpowiedzialnego | wspólny podflow: rola → `employees` → reguła `absences` → zastępca; używany przez wszystkie flow tworzące zadania |
| NOWY: zadania zaplanowane | codziennie `scheduled` → `todo` + powiadomienie |
| W3 / W0 | adres z `employees.email`, `assignee` jako link |
| W5 | dedup firm; ewentualnie osób po e-mailu |
| W13 | dostosowanie pól zapisywanych na leadzie (sprawdzić, które) |

**Sprawdzamy w praktyce w tym etapie:** przemianowanie pól zwrotnych relacji
(kod z `scripts/demo-schema-init.py`), filtry względne po datach w widokach,
co dziś wyzwala W3, skąd flow biorą adres e-mail odbiorcy.

**Widoki:** Pipeline (kanban), Leady do zakwalifikowania, Utknięte, Moje zadania
(do zrobienia), Moje zaplanowane, Osoby tylko do spotkań.

**Dane testowe:** `seed-test-data --stage 1` (zestaw wyżej).

**Test akceptacyjny (S1, część 1):**
1. Formularz: powstaje osoba, lead z `primary_person` i zadanie „Zakwalifikuj".
   Drugi submit z tym samym e-mailem nie tworzy duplikatu osoby.
2. Lead → SQL → przycisk: powstaje dokładnie jedna szansa na kanbanie z
   pierwszym wierszem historii; drugi klik nic nie tworzy.
3. Przeciągnięcie szansy przez etapy: wiersze historii, `stage_changed_at`.
4. Szansa przegrana z powodem; zadanie z `scheduled_for` jutro pojawia się w
   „Moje zaplanowane", po dacie w „Moje zadania".
5. Urlop handlowca (`absences`) + zadanie z terminem w jego trakcie trafia do
   zastępcy.
6. Formularz od osoby `Tylko spotkania`: brak leada, wpis w `activities`.

**Wyjście:** zespół może prowadzić leady i szanse od zgłoszenia do wygranej lub
utraty, bez spotkań i ofert.

---

## Etap 2 — spotkania i cal.com

**Tabele:** `meetings` (z `external_id`, `owner`, `attendees`), relacje do
`sale_opportunities`, `tasks`, `activities`.

**Flow:**

| Flow | Zmiana |
|---|---|
| NOWY: rezerwacje cal.com (zastępuje W7) | webhook utworzenia / zmiany terminu / anulowania; osoby po e-mailu, `attendees`, `owner` z `employees.email`, `meeting_type` z mapowania `eventTypeId`, link do szansy wg reguł z v4 |
| W6a (analiza spotkania) | `owner` i `attendees`, wynik w polach i statusie; zadania weryfikacyjne usunięte (Dodatek A) |

**Konfiguracja cal.com (w chmurze):** osobne typy wydarzeń dla discovery,
audytu i demo; webhooki; konta metodyczek.

**Sprawdzamy w praktyce:** dostępność i ładunek webhooków w używanym planie,
link do rezerwacji audytu z identyfikatorem szansy i e-mailem w parametrach
(pomysł z v4, „Do sprawdzenia w praktyce").

**Widoki:** Spotkania bez typu, Audyty w toku (częściowo).

**Dane testowe:** `seed-test-data --stage 2`.

**Test akceptacyjny (S1, część 2):**
1. Anna rezerwuje discovery: spotkanie ma typ, uczestnika Annę, właściciela
   handlowca i jest przypięte do jej jedynej otwartej szansy.
2. Zmiana terminu aktualizuje spotkanie, anulowanie ustawia `cancelled`.
3. Rezerwacja od nieznanego e-maila tworzy minimalną osobę.
4. Rezerwacja osoby `Tylko spotkania`: spotkanie jest, szansy ani leada nie ma.
5. Wklejenie transkrypcji i klik „Generuj analizę": status przechodzi do
   szkicu w kilka sekund, bez zadania.

**Wyjście:** każde spotkanie z cal.com ląduje w CRM z uczestnikami i typem.

---

## Etap 3 — audyty i oceny

**Tabele:** `assessments` (z `self_assessment`, `manager_needs`, `person`).
Na `sale_opportunities` dochodzą relacje `to_be_audited`, `audited`,
`participants` i przycisk „Generuj zadania audytowe"
(`audit_tasks_status`, `audit_tasks_note`, `audit_scope` są polami zwykłymi
od etapu 1).

**Flow:**

| Flow | Zmiana |
|---|---|
| NOWY: „Generuj zadania audytowe" | zadanie `audit_prep` na osobę z `to_be_audited`, idempotentne |
| W2 | przejście → `audit`: w B2C dopisanie kupującego do `to_be_audited` i zadania |
| NOWY: przeniesienie po ocenie | utworzenie `assessments` → osoba z `to_be_audited` do `audited` |
| W8 (needs summary) | ścieżka przez `assessments.person`; zadania usunięte (Dodatek A) |
| NOWY: przypomnienie o szkicach AI | codziennie rekordy `ai_draft_ready` starsze niż 24 h → zadanie `approve_ai_draft` (jedno na rekord) |

**Dane testowe:** `seed-test-data --stage 3`.

**Test akceptacyjny (S2, B2B Acme):**
1. Szansa B2B z trzema osobami w `to_be_audited` i przeniesieniem na etap
   Audyt → „Generuj zadania audytowe" tworzy trzy zadania dla metodyczki.
   Drugi klik niczego nie dubluje.
2. Trzy rezerwacje audytu (cal.com) → trzy spotkania z właściwymi uczestnikami.
3. Trzy oceny → wszyscy trzej przenoszą się do `audited`, `to_be_audited` puste.
4. Podpisanie umowy: `participants` = dwie osoby; trzecia (Karol) jest w
   `audited`, nie w `participants`.
5. Szkic needs summary zostawiony na dobę → powstaje jedno zadanie
   `approve_ai_draft`; po zatwierdzeniu nie powstaje drugie.

**Wyjście:** pełny proces audytowy B2C i B2B bez ręcznego linkowania uczestników.

---

## Etap 4 — rekomendacje i oferty

**Tabele:** `recommendations`, `offers`, `pricing`, `document_templates`,
`testimonials`, `training_descriptions`, `recommendation_packages`,
`package_variants_*`, `package_core_slides`, `selected_package_variants_*`,
`materials`, `newsletter_stats` (bez zmian względem obecnego
`init-schema.py`, poza `offers` i `recommendations`); `offers`: bez
`template_name`, z `approved_total`, `version_status` / `version_note`,
statusem `approved`; relacje tasków do `recommendation` i `offer`.

**Flow:**

| Flow | Zmiana |
|---|---|
| W1 generate_offer | źródło: `sale_opportunities`; kupujący z `person`; osoby oferty z `recommendations.person`; szablon nadal z `offers.document_templates`; zadania „review offer" i „generation failed" usunięte (Dodatek A) |
| W6b, W9, W10 | `sale_opportunities`; zadania wg Dodatku A |
| NOWY: `approved` | zapis `approved_total` i aktualizacja `deal_value` |
| NOWY: „Utwórz nową wersję" | kopia oferty z rekomendacjami i `selected_package_variants_*` (D4) |
| W2 | przejście → `recommendation`: zadanie „Przygotuj ofertę" |

Narzędzia importu katalogów (`import-pricing`, `import-packages`,
`import-testimonials`) uruchamiane po utworzeniu tabel.

**Dane testowe:** najpierw skrypty importu katalogów, potem
`seed-test-data --stage 4`.

**Test akceptacyjny (S1 część 3 i S4):**
1. B2C: rekomendacja Anny, oferta z ceną, generowanie pliku, status
   `draft` → `approved` → `sent` → `accepted`; `deal_value` równe
   `approved_total`.
2. B2B: oferta v1 dla trzech osób, „Utwórz nową wersję" i usunięcie
   rekomendacji Karola; v1 zachowuje swoją `approved_total`, v2 liczy dla dwóch.
3. Podpisanie umowy: stage → podpisana, `participants`, zadania dla finansów i
   metodyczki.

**Wyjście:** komplet procesu B2C i B2B od formularza do podpisu.

---

## Etap 5 — porządek: zadania, powiadomienia, dokumentacja

Cel: domknąć rzeczy przekrojowe, żeby etap 6 był tylko przełączeniem.

- Przegląd wszystkich zadań tworzonych przez flow względem Dodatku A: żadne
  poza zatwierdzonym zestawem nie powstaje.
- Przegląd wszystkich flow pod kątem czytania tytułów i tekstu zamiast pól
  SingleSelect (zasada „Tytuł jest dla zespołu").
- Wszystkie widoki z listy w specyfikacji odtworzone i opisane (checklista).
- Test Runner przechodzi dla S1–S5; dokumentacja (`README`, `docs/*.md`,
  `.ai/rules/*`, skill `n8n-flow`) zgodna z v4.

**Wyjście:** komplet testów zielony na instancji testowej.

---

## Etap 6 — przełączenie UAT i odbiór

1. Backup obecnego UAT (`make backup`), eksport workflowów n8n.
2. Odtworzenie bazy UAT według `docs/hard-reset.md` (krok 0 i `make init-schema`
   bez `--stage`), import wszystkich flow, `make dump-crm-schema`.
3. Dane testowe: `seed-test-data` dla etapów 1–4. Import historyczny ze
   starego CRM jest poza zakresem tego planu (sekcja niżej).
4. Webhooki cal.com przepięte na adresy UAT.
5. Usunięcie tabel `demo_*`; skrypty `demo-*` zostają w repo albo do archiwum.
6. Odbiór z zespołem: przejście S1 i S2 na ekranie.

**Rollback:** przywrócenie backupu UAT i dotychczasowych workflowów.

---

## Scenariusze akceptacyjne (do Test Runnera)

| # | Scenariusz | Etapy |
|---|---|---|
| S1 | B2C Anna: formularz → lead → szansa → discovery → audyt → demo → oferta → umowa | 1–4 |
| S2 | B2B Acme: lead z trzema osobami → szansa → trzy audyty → oferta dla trzech → v2 dla dwóch → umowa, participants = dwie osoby | 1–4 |
| S3 | Osoba `Tylko spotkania`: rezerwacja i formularz bez leada | 1–2 |
| S4 | Wersje ofert: zamrożona suma starej wersji | 4 |
| S5 | Urlop: zadanie w czasie nieobecności trafia do zastępcy | 1 |

---

## Poza zakresem: import ze starego `crm.xlsx`

Skrypt zasysający dane ze starego CRM zrobimy **w osobnej rozmowie, po
ustabilizowaniu schematu** (po etapie 5). Do tego czasu:

- `make init-data` i serwis `seed-service` (FastAPI z
  `init-data/Statusy_z_CRM_filled.xlsx`) piszą do tabel w starym kształcie
  (`leads`, `companies`, `participants`) i **nie wolno ich uruchamiać** na bazie
  v4. Serwis zostaje w `docker-compose.yml`, ale nieużywany.
- `scripts/seed-extra.py` pisze do starych tabel i pól (m.in. `leads`,
  `participants`, `offers.template_name`); zastępuje go nowy seed. Plik zostaje
  w repo do czasu zakończenia migracji.
- `docs/archive/fable/import_legacy_excel.py` i `.ai/pipedrive-clone-prd.md`
  §11 (mapowanie kolumn Excela) będą punktem wyjścia do importu; mapowanie
  trzeba będzie dopasować do ostatecznego schematu (rozbicie wiersza Excela
  na `persons`, `leads` i `sale_opportunities` z historią etapów jest już
  opisane w v4, „Mapowanie starych pól").

## Ryzyka planu

- **Największe flow:** W4v2 ma 56 węzłów, W1 44; przepięcie ich na `persons` /
  `sale_opportunities` to najcięższa praca i warto zacząć od etapu 1 z
  uwzględnieniem tej wielkości.
- **Wszystkie ID tabel i pól się zmieniają** (nowa baza). Stare flow z
  zaszytymi ID trzeba edytować, nie tylko przepinać (D5).
- **Niezweryfikowane na żywo:** przemianowanie pól zwrotnych, konwersja relacji
  do v3, webhooki cal.com w chmurze, filtry względne. Etap 1 i 2 wykrywają to
  najwcześniej.
- **Stare seedery pod ręką.** `make init-data`, serwis `seed-service` i
  `seed-extra.py` nadal są w repo i pasują do starego schematu; uruchomione
  przez pomyłkę na bazie v4 napiszą do nieistniejących pól albo utworzą
  rekordy w złym kształcie. Rozważyć komunikat ostrzegawczy w Makefile.
- **Seed etapami wymaga stabilnych kluczy.** Rekordy wcześniejszych etapów
  odnajduje po e-mailu osoby i nazwie szansy; zmiana tych danych w seedzie
  etapu 1 wymaga zmiany we wszystkich późniejszych.
- **`--stage` w `init-schema.py`** to nowy kod w skrypcie, który działa na
  produkcji; wymaga `--dry-run` i testu na pustej bazie testowej przed użyciem.

---

## Dodatek A — zadania tworzone dziś przez istniejące flow

Liczone z nazw węzłów w JSON-ach (nie z przeglądu logiki). Kolumna „Propozycja"
dotyczy polityki z v4 („Zasady tworzenia zadań"); to do zatwierdzenia (D6).

| Flow | Zadania (nazwy węzłów) | Propozycja |
|---|---|---|
| W0 | cykliczne z `task_templates` | zostaje (nie reaguje na zdarzenie) |
| W2 | „fill reason" przy utracie bez powodu | usunąć; widok „Utracone bez powodu" |
| W3 | powiadomienia o zadaniach | zostaje, adres z `employees` |
| W4v2 | T1o, T1c, T3, T5, „LLM" (dopasowanie osób i firm do potwierdzenia) | **do decyzji**: wymagają decyzji człowieka, ale nie mieszczą się w trzech przypadkach |
| W4v3 | „schedule discovery call", „client wrote again", „intake failed" | pierwsze → `qualify_lead` (przypadek 1); pozostałe do decyzji |
| W6a | verify, close verify, goals, fix-it | verify i fix-it usunąć (status i przypomnienie po dobie); goals do decyzji |
| W6b | goals, testimonials, „offer task for owner" i ich zamykanie | „offer task" → przejście → `recommendation`; pozostałe do decyzji |
| W8 | zweryfikuj needs summary, błąd generowania, uzupełnij oceny CEFR | pierwsze dwa usunąć; ostatnie do decyzji |
| W9 | zweryfikuj opis pakietu, błąd, uzupełnij wariant | jak W8 |
| W10 | uzupełnij pakiety, błąd aktualizacji | do decyzji |
| W13 | review AI assessment, błąd analizy | review → przypomnienie po dobie; błąd usunąć |
| W1 | review offer, generation failed | usunąć (stan w `status` / `generation status`) |

„Do decyzji" oznacza zadania typu „brakuje danych wejściowych, uzupełnij" i
„ręczne potwierdzenie dopasowania". Proponuję je zachować jako czwarty,
wąski przypadek („brakuje danych, bez których flow nie ruszy"), ale to decyzja
użytkownika.
