# Generowanie ofert PPTX — offer-service + W9

Feature: przycisk "Generuj ofertę" na leadzie → n8n zbiera dane i szablon,
woła mikroserwis, który tylko renderuje PPTX → n8n zapisuje wynik jako plik
w rekordzie `offers`, podlinkowany do leada.

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

**`offer-service` nie ma żadnej wiedzy o NocoDB** — zero zmiennych
`NOCODB_*`, zero odczytów/zapisów do bazy. To **czysty renderer**: dostaje
plik szablonu + dane, zwraca gotowy plik. Wszystko inne — skąd wziąć
szablon, jak złożyć dane, gdzie zapisać wynik, kiedy stworzyć rekord
`offers` — robi workflow `W9` w n8n. Model danych CRM może się zmieniać
(nowe pole, nowa tabela ocen) bez dotykania tego serwisu w ogóle.

## Kontrakt /render

`POST /render`, `multipart/form-data`:
- pole `template` — plik `.pptx` (n8n pobiera go z `offer_templates.file`)
- pole `data` — JSON string, kontekst renderu (patrz "Kontrakt szablonu" niżej)

Odpowiedź: wygenerowany plik `.pptx` (binarnie, `Content-Type` PPTX).
Ostrzeżenia z renderu (brakujące placeholdery, puste listy repeat) wracają
w nagłówku `X-Warnings` jako JSON-owa tablica stringów — n8n czyta ten
nagłówek i wrzuca go do `warnings` w rekordzie `offers`.

Serwis nie wie nic o `lead_id`, `offers`, uploadzie do NocoDB ani o tym, co
oznacza dowolne pole w `data` poza tym, że jakiś placeholder może je
referencować — to wszystko po stronie n8n.

## Kontrakt szablonu (dla nietechnicznych — edycja w PowerPoincie)

**Placeholdery** — wpisz `{{ścieżka}}` w dowolnym polu tekstowym lub komórce
tabeli. Ścieżka to zwykłe zagnieżdżenie kluczy w `data`, np. dla
`data = {"lead": {"contact_name": "Ala"}}` → `{{lead.contact_name}}`.
Żadne nazwy pól nie są wbudowane w serwis — to, co wpiszesz w szablonie,
musi się zgadzać z tym, co n8n włoży do `data`.

**Slajd powtarzalny** — wpisz w NOTATKACH slajdu (nie na slajdzie!)
`repeat:<nazwa>`, np. `repeat:participant`. Slajd powiela się raz na każdy
element listy `data["<nazwa>"]`. `<nazwa>` jest całkowicie dowolna —
`repeat:testimonial`, `repeat:goal`, cokolwiek — serwis nie ma zaszytej
listy dozwolonych nazw.

Wewnątrz takiej kopii element jest dostępny **na dwa sposoby**:
- z prefiksem: `{{participant.full_name}}`, `{{participant.a.o}}`
- bez prefiksu (klucze elementu są podnoszone na wierzch):
  `{{full_name}}`, `{{a.o}}`

Dzięki temu skróty typu `{{a.o}}` działają bez pisania
`{{participant.a.o}}`. Uwaga: podniesione klucze przesłaniają na tym jednym
slajdzie klucze o tej samej nazwie z `data` (forma z prefiksem zawsze
zostaje dostępna).

**Częsta pułapka:** placeholder z jednym nawiasem zamykającym
(`{{testimonial.name}` zamiast `{{testimonial.name}}`) **nie jest w ogóle
rozpoznawany** — nie podstawi się i NIE pojawi się w `warnings`, tylko
zostanie w ofercie jako goły tekst. Jeśli w wygenerowanym pliku widzisz
`{{coś}`, to literówka w szablonie, nie błąd danych.

Dziś w użyciu (ustalone z n8n, nie z serwisem):
- `repeat:participant` → `{{participant.full_name}}`, `{{participant.position}}`,
  `{{participant.needs_summary}}`, oceny zagnieżdżone pod `a`:
  `{{participant.a.o}}` / `.r` / `.a` / `.f` / `.c`
  (overall/range/accuracy/fluency/communication)
- `repeat:testimonial` → `{{testimonial.title}}`, `{{testimonial.content}}`,
  `{{testimonial.client_name}}`

Pusta lista (albo brak klucza w `data`) → slajd jest usuwany z ostrzeżeniem
w `warnings`, nie błędem.

**Jedna zasada formatowania:** trzymaj cały `{{placeholder}}` w jednym stylu
(nie pogrubiaj połowy). Serwis radzi sobie z rozbiciem na runy, ale wtedy cały
tekst akapitu przyjmuje styl pierwszego fragmentu. W praktyce: zaznacz placeholder,
nadaj styl całości.

## Deployment

Serwis jest już wpięty w stack przez `fragments/offer-service.yml` (dołączony
w `docker-compose.yml` → `include:`) — jedyny customowy (`build:`) obraz w
tym compose, reszta serwisów to gotowe obrazy. Zero zmiennych środowiskowych
poza opcjonalnym `PORT`.

1. `docker compose up -d --build offer-service` (pierwszy raz i po każdej
   zmianie w `app.py`/`renderer.py`/`requirements.txt` — `make up` sam z
   siebie nie buduje obrazów).
2. Sanity: `docker compose exec n8n wget -qO- http://offer-service:8000/health`
   → `{"ok": true}`.
3. Zaimportuj `fable/W9_generate_offer.json` (13 node'ów): payload przycisku →
   `Assemble render data` (Edit Fields) → pobranie aktywnego szablonu +
   binarki → POST multipart do `/render` → upload wyniku do NocoDB →
   rekord w `offers` (`status=draft`, `file`, `data_json`, `warnings`
   z nagłówka `X-Warnings`) → link do leada → task review / task błędu.
   Podmień jedyny placeholder `__LNK_OFFER_LEAD__` (ID pola Link
   `offers`→`leads`, patrz `fable/README.md` §1).
4. Na tabeli `leads` dodaj pole **Button** "Generuj ofertę" → webhook na
   workflow z kroku 3. Sensowny warunek widoczności:
   `offer_prep_status = draft_ready` (ustawiane przez W6b).
5. Wgraj pierwszy szablon do `offer_templates` (`active=true`).

## Tabele `offer_templates`/`offers` (używane przez n8n, nie przez serwis)

Jak reszta modelu danych CRM (`.ai/PRD.md` §5) — tabele NIE powstają z pliku
migracji, tylko ręcznie przez NocoDB Creator UI.

**`offer_templates`**: `name` (text), `file` (Attachment — tu wgrywasz .pptx),
`active` (checkbox), `notes` (text). n8n bierze najnowszy rekord z `active=true`.

**`offers`**: `title` (text), `status` (select: draft/sent/accepted/rejected),
`price` (currency), `template_name` (text), `file` (Attachment — tu ląduje
wynik), `data_json` (LongText — snapshot danych użytych do oferty, pod historię
i regenerację), `warnings` (LongText), `lead` (Links → leads).

> `data_json` to Twój wymóg "historii ofert" z pierwotnego docx: każda oferta
> zachowuje zamrożony stan danych, z których powstała — nawet jeśli lead
> później się zmieni, wiadomo, co dokładnie wysłano.

## Ograniczenia (świadome)

- Rendering podmienia tekst; NIE przelicza układu — jeśli
  `{{participant.needs_summary}}` jest bardzo długie, może wyjść poza pole
  (jak w każdym szablonie). Projektuj slajdy z zapasem; ewentualnie skracaj
  długie pola w danych.
- Repeat działa na całych slajdach, nie na wierszach tabeli. Gdyby kiedyś
  trzeba było "N uczestników w jednej tabeli na jednym slajdzie" — to osobne
  rozszerzenie (repeat na wierszu `<a:tr>`), do zrobienia gdy zajdzie potrzeba.
- Serwis zakłada, że `data` przysłane przez n8n jest poprawne — literówka
  w nazwie pola w Edit Fields → pusty string + warning, nie błąd. Dlatego
  W9 wrzuca `warnings` do opisu taska review — przejrzyj je przy pierwszych
  ofertach.
- Nazwa w `repeat:<nazwa>` i prefiks placeholdera muszą być identyczne
  (patrz kontrakt szablonu) — to jedyna reguła narzucona przez serwis,
  wszystko inne w `data` jest w pełni dowolne.
- **W9 czyta uczestników i referencje wprost z payloadu przycisku NocoDB**
  (`_nc_m2m_Leads_Participants[].Participants`,
  `_nc_m2m_Leads_Testimonials[].Testimonials`) zamiast dociągać je osobnymi
  zapytaniami — dlatego workflow ma 13, a nie 21 node'ów. Cena: to dokładnie
  ta zależność od kształtu payloadu, przed którą ostrzega `.ai/PRD.md` §11
  pkt 3. Po każdym upgradzie NocoDB sprawdź na VPS-B, czy pola `_nc_m2m_*`
  nadal przychodzą rozwinięte.
- **Endpoint `/links/{fieldId}/records/{id}` zwraca tylko `Id` + wartość
  wyświetlaną**, nie pełny rekord (zweryfikowane: `{{t.title}}` się
  rozwiązywało, `{{t.content}}` nie). Dlatego oceny NIE są dociągane po
  linku: W9 pobiera **całą tabelę `Assesments` jednym zapytaniem** i dopasowuje
  je do uczestników po `Participant.Id`, biorąc rekord o najnowszym
  `UpdatedAt`. Przy dużej liczbie ocen (setki+) to zacznie być kosztowne —
  wtedy dołóż filtr `where` po stronie zapytania.
- Uczestnik bez żadnego rekordu w `Assesments` → oceny puste (`{{participant.a.o}}`
  itd. jako pusty string + warning), `needs_summary` spada z powrotem na pole
  z tabeli `Participants`.

## Testy

`pytest offer-service/ -v` — bez zależności od NocoDB, bez sieci:
- `test_renderer.py` — repetycja slajdów per element (dowolna nazwa, nie
  tylko "participant"/"testimonial"), split placeholdera między runy, pusta
  lista / brak klucza → drop slajdu z ostrzeżeniem, brakująca/zagnieżdżona
  wartość → pusty string + warning.
- `test_app.py` — realne wywołanie endpointu `/render` (przez FastAPI
  bezpośrednio + smoke test przez prawdziwy multipart request), sprawdza
  wynikowy plik i nagłówek `X-Warnings`.
