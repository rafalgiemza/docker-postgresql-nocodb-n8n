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
python-pptx) w tym samym compose: n8n woła go po HTTP (`http://offer-service:8000`).
Rdzeń renderujący (`renderer.py`) jest czysty i przetestowany offline — bez
tej separacji nie dałoby się go sensownie testować.

**Serwis nie czyta już `leads`/`participants`/`testimonials`/`companies`/`assesments`
sam** — to robi workflow `W9` w n8n (NocoDB nody + Edit Fields), które składa
gotowy obiekt `data` i wysyła go w ciele `/generate`. `offer-service` czyta z
NocoDB wyłącznie `offer_templates` (szablon) i pisze do `offers` (wynik) —
patrz „Kontrakt /generate" niżej.

## Kontrakt /generate

`POST /generate` z ciałem:
```json
{
  "lead_id": 123,
  "data": {
    "lead": {"contact_name": "...", "value": 5000, "...": "..."},
    "company": {"name": "..."},
    "participants": [
      {"full_name": "...", "position": "...", "needs_summary": "...",
       "a": {"o": "B2", "r": "B1-B2", "a": "B2", "f": "B1", "c": "B2"}}
    ],
    "testimonials": [{"title": "...", "content": "...", "client_name": "..."}],
    "offer": {"date": "27.07.2026", "price": 5000, "variant": "",
              "participants_count": 1}
  }
}
```
`data` idzie 1:1 do `renderer.py` jako kontekst placeholderów — kształt tego
obiektu **jest** kontraktem szablonu (sekcja niżej). `lead_id` osobno, bo
służy tylko do tytułu/linkowania rekordu `offers`, nie do renderu.

## Kontrakt szablonu (dla nietechnicznych — edycja w PowerPoincie)

**Placeholdery** — wpisz `{{ścieżka}}` w dowolnym polu tekstowym lub komórce tabeli:
- `{{lead.contact_name}}`, `{{lead.value}}`, `{{company.name}}`
- `{{offer.date}}`, `{{offer.variant}}`, `{{offer.participants_count}}`

**Slajd powtarzalny** — wpisz w NOTATKACH slajdu (nie na slajdzie!):
- `repeat:participants` → slajd powiela się raz na uczestnika; użyj
  `{{participant.full_name}}`, `{{participant.position}}`,
  `{{participant.needs_summary}}`, i oceny z tabeli `Assesments`
  (zagnieżdżone pod `a`): `{{participant.a.o}}`, `{{participant.a.r}}`,
  `{{participant.a.a}}`, `{{participant.a.f}}`, `{{participant.a.c}}`
  (overall/range/accuracy/fluency/communication)
- `repeat:testimonials` → raz na referencję; `{{testimonial.title}}`,
  `{{testimonial.content}}`, `{{testimonial.client_name}}`

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

Button → parse lead_id → **n8n zbiera dane** (lead, participants + ich
`Assesments`, testimonials, company — kilka node'ów NocoDB/HTTP Request +
pętla po uczestnikach) → Edit Fields składa to w kształt z „Kontrakt
/generate" → POST `{lead_id, data}` do offer-service (timeout 120s, bo render
trwa) → **dwie gałęzie**: sukces → task "Sprawdź wygenerowaną ofertę" (z
warnings w opisie) + activity; błąd → task "BŁĄD generowania" + activity
`automation_error`. Serwis nigdy nie wysyła oferty sam — tworzy `draft` i
zostawia człowiekowi decyzję (spójne z całą filozofią: automat przygotowuje,
człowiek zatwierdza).

## Ograniczenia (świadome)

- Rendering podmienia tekst; NIE przelicza układu — jeśli
  `{{participant.needs_summary}}` jest bardzo długie, może wyjść poza pole
  (jak w każdym szablonie). Projektuj slajdy z zapasem; ewentualnie skracaj
  długie pola w danych.
- Repeat działa na całych slajdach, nie na wierszach tabeli. Gdyby kiedyś
  trzeba było "N uczestników w jednej tabeli na jednym slajdzie" — to osobne
  rozszerzenie (repeat na wierszu `<a:tr>`), do zrobienia gdy zajdzie potrzeba.
- Serwis zakłada, że `data` przysłane przez n8n jest poprawne — literówka
  w nazwie pola w Edit Fields → pusty string + warning w rekordzie oferty,
  nie błąd. Dlatego W9 wrzuca `warnings` do opisu taska review — przejrzyj
  je przy pierwszych ofertach.
- Skoro dane zbiera teraz n8n, a nie `app.py`, każda zmiana w modelu danych
  (nowe pole uczestnika, inna tabela ocen) wymaga zmiany w workflow W9
  (node Edit Fields), NIE w kodzie serwisu — to był cel tej zmiany.

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
