# Zasady wspólne — architektura automatyzacji CoAction CRM

Doktryna nadrzędna dla wszystkich flow n8n + NocoDB w tym repo. Ustalona z
userem 2026-09-26 na podstawie analizy `W1_generate_offer.json`,
`schema_map.json` i `fragments/file-renderer-service.yml`. Mechanikę
techniczną (nazewnictwo node'ów, "Get one base", pole `status`) opisuje
`.claude/skills/n8n-flow/SKILL.md` — ten plik odpowiada na pytanie **dlaczego**
flow są podzielone tak, jak są, i jak dzielić nowe.

Szczegóły per temat: [n8n.md](n8n.md) (mechanika flow), [ai-n8n.md](ai-n8n.md)
(sub-flow AI), [nocodb.md](nocodb.md) (dostęp do danych).

## 1. Dane pobieramy natywnym node'em NocoDB

W n8n dane z CRM czytamy/piszemy przez natywny node `n8n-nodes-base.nocoDb`
(get/getAll/create/update, `resource: linkrow` dla relacji M2M), nie przez
`httpRequest` do API NocoDB. Wyjątki tylko dla endpointów, których node nie
pokrywa (np. `/api/v2/storage/upload`). Szczegóły i historia w
[nocodb.md](nocodb.md).

## 2. Każdy krok automatyzacji ma feedback w polu single select

User nietechniczny musi widzieć, na jakim etapie jest flow, patrząc na wiersz
w NocoDB — nie w logach n8n. Feedback zawsze przez pole typu SingleSelect,
zapisywane w konkretnych momentach (start / przed krokiem kosztownym-lub-AI /
sukces / błąd). Generyczna konwencja pola `status` — patrz
`.claude/skills/n8n-flow/SKILL.md` §3.

## 3. Proces AI jest architektonicznie odseparowany

Każdy fragment flow, który woła LLM, jest wydzielony — osobny flow (własny
Button/webhook), a nie krok wewnątrz flow, które robi coś innego (zbieranie
danych, render pliku). Kontrakt takiego procesu jest wąski:

- **wejście**: tekst (kontekst złożony z danych CRM w jednym węźle),
- **wyjście**: tekst zapisany w **jednym** dedykowanym polu (np.
  `needs_summary`, `generated_text`) — AI nie tworzy struktur, nie tworzy
  innych wierszy, nie wywołuje kolejnych efektów ubocznych,
- **feedback**: własne pole single-select o semantyce cyklu recenzji
  (draft → zaakceptowany/odrzucony przez człowieka), odrębne od generycznego
  `status`.

Pełne zasady i konwencja nazw wartości: [ai-n8n.md](ai-n8n.md). Przykłady w
repo: `W8_assessment_needs_summary.json` (pole `needs_summary`),
`W9_offer_package_texts.json` (pole `generated_text`).

## 4. Trzy fazy dla każdego procesu kończącego się plikiem

Flow, który ma wyprodukować dokument (PPTX/DOCX) z szablonu, jest rozbity na
trzy niezależne fazy — nigdy nie łącz ich w jednym flow/nodzie:

1. **Tworzenie treści** — teksty, które trafią do dokumentu; może w tym
   uczestniczyć AI (zasada 3), ale nie musi (patrz `W10_recommendation_rationale.json`
   — czyste deterministyczne sklejanie tekstu, bez AI, bez pola statusu — to
   świadomy wyjątek, nie domyślny wzorzec). Wynik: tekst osiada w polu tabeli
   NocoDB.
2. **Pomocnicze wpisy w bazie, jeśli render ich potrzebuje** — np. wiersze w
   tabelach selekcji (`selected_package_variants_cores/others` w tym repo),
   które reprezentują "co konkretnie wybrano do TEJ oferty", odrębne od
   tabel katalogowych z definicjami (`package_variants_cores/others`). Ta
   faza nie zawsze jest potrzebna — pomiń ją, jeśli render czyta wyłącznie
   dane z fazy 1.
3. **Generowanie finalnego pliku** — jeden flow (`W1_generate_offer.json`)
   scala już-istniejące dane z faz 1-2 w jedną płaską strukturę (jeden node
   typu Set, `executeOnce`, np. "Assemble offer data"), woła bezstanowy
   serwis renderujący (szablon + dane → plik), wgrywa wynik, aktualizuje
   rekord i loguje. Ten krok **nigdy** nie ma logiki AI i **nigdy** nie
   zawiera osobnej logiki tworzenia treści — tylko odczyt-złóż-wyrenderuj.

Renderer (`file-renderer-service`) jest świadomie bezstanowy i ZERO
integracji z NocoDB (brak zmiennych `NOCODB_*` w jego konfiguracji) — wszystkie
odczyty z bazy dzieją się w n8n PRZED wywołaniem serwisu, wszystkie zapisy PO.
Nie dodawaj serwisowi renderującemu żadnej wiedzy o NocoDB, nawet "tymczasowo".

## 5. Tytuł rekordu jest dla zespołu, nie dla n8n (schemat v4)

Pole tytułowe rekordu (`name`, `title`, `full_name`, `lead_name` itd.) służy
ludziom: pojawia się w linkach i listach, żeby było widać, o jaki wpis chodzi,
zanim się go otworzy. Zespół nazywa wpisy dowolnie i zmienia nazwy w każdej
chwili. **Dla n8n deterministyczne są tylko pola SingleSelect** (oraz linki i
klucze takie jak `email`, `external_id`):

- flow nigdy nie czyta tytułu, żeby zdecydować, co zrobić: rodzaj zadania
  rozpoznaje po `tasks.task_type`, typ spotkania po `meetings.meeting_type`,
  etap po `sale_opportunities.stage`, segment po `segment`; tytuły tylko
  **zapisuje**,
- każde rozróżnienie, na którym opiera się automatyzacja, ma własne pole
  SingleSelect; jeśli go brakuje, dodajemy pole zamiast parsować tekst,
- sprawdzenie „czy to już istnieje" (idempotencja) robimy po linkach i
  SingleSelectach, nie po treści tytułu,
- opcji SingleSelect nie przemianowujemy w UI bez zmiany flow (porównują
  dokładne wartości).

## 6. Kiedy flow tworzy zadanie (schemat v4)

Przycisk generujący wynik (analiza, `needs_summary`, oferta, slajdy) zwraca go w
kilka sekund, a stan pokazuje pole `status`; **zadanie po jego kliknięciu nie
powstaje**. Zadanie tworzymy tylko, gdy człowiek musi coś zrobić, a rekord sam
tego nie pokaże:

1. potencjalny klient wypełnił formularz (`task_type` = `qualify_lead`),
2. szansa sprzedaży przechodzi na etap wymagający uwagi innego członka zespołu
   (tabela przejść w `docs/archive/fable/nocodb_crm_schema_v4.md`),
3. nikt nie zatwierdził szkicu AI od wczoraj (dzienny flow, `approve_ai_draft`).

Wyjątkiem jest przycisk, którego jedynym celem jest utworzenie zadań
(„Generuj zadania audytowe"). Kontakty z terminem („odezwać się za 3 dni")
handlowiec zapisuje sam jako zadanie ze `scheduled_for` i statusem `scheduled`.
Adresata zadania wyznacza wspólny podflow: rola → `employees` → reguła
`absences` (zastępca). Rodzaj zadania zawsze zapisujemy w `task_type`.
