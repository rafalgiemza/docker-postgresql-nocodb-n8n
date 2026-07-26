# Generowanie ofert PPTX — offer-service + W9

Feature: przycisk "Generuj ofertę" na leadzie → n8n woła mikroserwis →
serwis renderuje PPTX z **szablonu trzymanego w bazie** + danych leada →
wynik ląduje jako plik w rekordzie `offers`, podlinkowany do leada.

Kluczowa własność (wymaganie CEO): **szablon to plik .pptx w NocoDB**. Ktoś
zmienia układ slajdu w PowerPoincie, podmienia załącznik w tabeli
`offer_templates`, zaznacza `active` — i następne oferty używają nowego układu.
Zero zmian w kodzie, zero deployu.

## Dlaczego osobny serwis, a nie node w n8n

Renderowanie .pptx to manipulacja binarna (rozpakuj ZIP, edytuj XML, spakuj) —
w Code node n8n byłoby to kruche i nietestowalne. Mikroserwis (FastAPI +
python-pptx) w tym samym compose: n8n woła go po HTTP (`http://offer-service:8000`),
serwis gada z NocoDB po API. Rdzeń renderujący (`renderer.py`) jest czysty
i przetestowany offline — bez tej separacji nie dałoby się go sensownie testować.

## Kontrakt szablonu (dla nietechnicznych — edycja w PowerPoincie)

**Placeholdery** — wpisz `{{ścieżka}}` w dowolnym polu tekstowym lub komórce tabeli:
- `{{lead.contact_name}}`, `{{lead.value}}`, `{{company.name}}`
- `{{offer.date}}`, `{{offer.variant}}`, `{{offer.participants_count}}`

**Slajd powtarzalny** — wpisz w NOTATKACH slajdu (nie na slajdzie!):
- `repeat:participants` → slajd powiela się raz na uczestnika; użyj
  `{{p.full_name}}`, `{{p.position}}`, `{{p.cefr_overall}}`, `{{p.cefr_range}}`,
  `{{p.cefr_accuracy}}`, `{{p.cefr_fluency}}`, `{{p.cefr_communication}}`,
  `{{p.needs_summary}}`
- `repeat:testimonials` → raz na referencję; `{{t.title}}`, `{{t.content}}`,
  `{{t.client_name}}`

**Jedna zasada formatowania:** trzymaj cały `{{placeholder}}` w jednym stylu
(nie pogrubiaj połowy). Serwis radzi sobie z rozbiciem na runy, ale wtedy cały
tekst akapitu przyjmuje styl pierwszego fragmentu. W praktyce: zaznacz placeholder,
nadaj styl całości.

## Tabele do utworzenia

Jak reszta modelu danych CRM (`.ai/PRD.md` §5) — tabele NIE powstają z pliku
migracji, tylko ręcznie przez NocoDB Creator UI, na tej samej bazie co
`leads`/`participants`/`testimonials`. Zrób to PRZED pierwszym uruchomieniem
serwisu — `/health` (krok 3 w Deployment) sprawdza ich obecność.

**`offer_templates`**: `name` (text), `file` (Attachment — tu wgrywasz .pptx),
`active` (checkbox), `notes` (text). Reguła: serwis bierze najnowszy rekord
z `active=true`.

**`offers`**: `title` (text), `status` (select: draft/sent/accepted/rejected),
`price` (currency), `template_name` (text), `file` (Attachment — tu ląduje
wynik), `data_json` (LongText — snapshot danych użytych do oferty, pod historię
i regenerację), `warnings` (LongText), `lead` (Links → leads).

> `data_json` to Twój wymóg "historii ofert" z pierwotnego docx: każda oferta
> zachowuje zamrożony stan danych, z których powstała — nawet jeśli lead
> później się zmieni, wiadomo, co dokładnie wysłano.

## Deployment

Serwis jest już wpięty w stack przez `fragments/offer-service.yml` (dołączony
w `docker-compose.yml` → `include:`) — jedyny customowy (`build:`) obraz w
tym compose, reszta serwisów to gotowe obrazy. Wymaga `NC_API_TOKEN` i
`NC_CRM_BASE_ID` w `.env` (patrz `.env.example`).

1. Utwórz tabele `offer_templates`/`offers` (patrz sekcja wyżej).
2. `docker compose up -d --build offer-service` (pierwszy raz i po każdej
   zmianie w `app.py`/`renderer.py`/`requirements.txt` — `make up` sam z
   siebie nie buduje obrazów).
3. Sanity: `docker compose exec n8n wget -qO- http://offer-service:8000/health`
   → powinno zwrócić `{"ok": true, ...}` z mapą tabel.
4. Zaimportuj `fable/W9_generate_offer.json` w n8n, podmień placeholdery
   (`__NOCODB_URL__`, `__TBL_TASKS__`, `__TBL_ACTIVITIES__`, `__EMAIL_PRZEMEK__`)
   tak samo jak resztę workflowów (`fable/README.md` §1), podepnij credential
   „NocoDB Token" pod node'y HTTP Request, aktywuj.
5. Na tabeli `leads` dodaj pole **Button** "Generuj ofertę" → webhook POST na
   `.../webhook/w9-generate-offer` (jak Twój przycisk "run ai"). Sensowny
   warunek widoczności: `offer_prep_status = draft_ready` (ustawiane przez W6b).
6. Wgraj pierwszy szablon do `offer_templates` (`active=true`).

## Jak działa W9

Button → parse lead_id → POST do offer-service (timeout 120s, bo render trwa) →
**dwie gałęzie**: sukces → task "Sprawdź wygenerowaną ofertę" (z warnings
w opisie) + activity; błąd → task "BŁĄD generowania" + activity `automation_error`.
Serwis nigdy nie wysyła oferty sam — tworzy `draft` i zostawia człowiekowi
decyzję (spójne z całą filozofią: automat przygotowuje, człowiek zatwierdza).

## Ograniczenia (świadome)

- Rendering podmienia tekst; NIE przelicza układu — jeśli `{{p.needs_summary}}`
  jest bardzo długie, może wyjść poza pole (jak w każdym szablonie). Projektuj
  slajdy z zapasem; ewentualnie skracaj długie pola w danych.
- Repeat działa na całych slajdach, nie na wierszach tabeli. Gdyby kiedyś
  trzeba było "N uczestników w jednej tabeli na jednym slajdzie" — to osobne
  rozszerzenie (repeat na wierszu `<a:tr>`), do zrobienia gdy zajdzie potrzeba.
- Serwis zakłada, że placeholdery i markery są poprawne. Literówka w `{{p.cerf_overall}}`
  (zamiast cefr) → pusty string + warning w rekordzie oferty, nie błąd. Dlatego
  W9 wrzuca `warnings` do opisu taska review — przejrzyj je przy pierwszych ofertach.

## Testy

`renderer.py` przetestowany offline w `offer-service/test_renderer.py`
(repetycja slajdów per uczestnik, split placeholdera między runy, pusta
lista → drop slajdu z ostrzeżeniem, brakująca wartość → pusty string),
`pytest offer-service/test_renderer.py -v`, bez zależności od NocoDB.

Do Test Runnera (`fable/test_workflows.py`) dochodzi grupa `W9`: generowanie
E2E przez webhook `w9-generate-offer` na leadzie testowym + asercja, że
powstał rekord `offers` z niepustym `file` i że liczba slajdów repeat =
liczba participants. Wzorzec jak w istniejących testach W6b w tym samym
pliku.
