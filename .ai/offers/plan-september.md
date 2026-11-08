# Rich text (markdown) w file-renderer-service

Cel: pola NocoDB typu Long Text z włączonym "rich text" (markdown) mają być
renderowane w PPTX/DOCX z prawdziwym formatowaniem, nie ze spłaszczonym
tekstem zawierającym literalne `**`/`_`/`<u>` itd.

**Nie dotyczy `fragments/file-renderer-service.yml`** — to czysty
compose-fragment (build, limity CPU/RAM), zero logiki. Cała zmiana leży w
`file-renderer-service/*.py`. n8n (W1, node "Assemble offer data") już dziś
przekazuje pola 1:1 bez żadnego stripowania markdownu — zero zmian po
stronie n8n.

## Potwierdzona składnia (empirycznie, `.ai/rich-text.md`)

| Element | Składnia NocoDB |
|---|---|
| bold | `**text**` |
| italic | `_text_` (underscore, nie `*`) |
| underline | `<u>text</u>` (surowy HTML, markdown tego nie ma natywnie) |
| strikethrough | `~słowo~` (pojedyncza tylda) |
| inline/blok code | `` `code` `` / ```` ```code``` ```` |
| nagłówki | `# h1`, `## h2`, `### h3` |
| złamanie linii | `<br>` lub `\n` |
| obrazek | `![alt](url)` |
| link | `[text](url)` |
| task list | `- [ ] item`, `- [x] item` |
| numbered list | `1. item` |
| bullet list | `- item` |
| quote | `> quote` |

## Decyzje (podjęte w rozmowie 2026-09-26)

1. **Pełny zakres** — wszystkie elementy z tabeli wyżej, nie tylko
   bold/italic/underline/strike. User: "nie będę tłumaczyć nietechnicznym
   czego nie klikać, nikt nie zapamięta" → obsłużyć wszystko, co edytor
   NocoDB potrafi wyprodukować.
2. **Brak warningów na start** — pełne wsparcie, bez ostrzeżeń o
   niewspieranych przypadkach. Jeśli po pierwszym deployu/teście coś nie
   zadziała dobrze, user sam poprosi o warning w konkretnym miejscu.
3. **Strikethrough tylko dla pojedynczych słów** — `~(\S+)~`, żadnych
   spacji w środku. Powód: `~~` (GFM) nie jest tym, co emituje NocoDB
   (pojedyncza tylda), a pojedyncza tylda bez ograniczenia do jednego słowa
   kolidowałaby z naturalnym użyciem w tekście biznesowym (np. "~10 godzin").
4. **Parser: mistune + 2 własne reguły inline** (nie ręczne regexy, nie
   pełna własna implementacja) — dla `<u>...</u>` i `~słowo~`, bo to
   konstrukcje niestandardowe, których żaden parser markdown nie zna z
   pudełka. Bold/italic/code/heading/list/quote/link/image obsługuje mistune
   natywnie.
5. **Obrazki w PPTX: osobny shape best-effort.** PPTX nie ma pojęcia
   "obrazek w środku tekstu" (text_frame i picture to zawsze niezależne
   shape'y) — obrazek wstawiany jako osobny shape na slajdzie, pozycjonowany
   względem bounding-boxa placeholdera tekstowego, przeskalowany do jego
   szerokości. Nie prawdziwy inline flow — do sprawdzenia wizualnie po
   wdrożeniu (Faza 3), może nachodzić na tekst przy dużym obrazku.
6. **Fetch obrazków: TAK, z limitami.** Jedyne miejsce w serwisie robiące
   zapytania sieciowe (odstępstwo od "zero integracji zewnętrznych" z
   README) — `https://` only, timeout 5s, limit 10MB, brak retry, błąd
   fetchu → obrazek pomijany po cichu (zgodne z decyzją #2, brak warningów
   na razie). Endpointy `/render`/`/render-docx` w `app.py` są `async def`,
   więc blokujący fetch chwilowo zatrzyma event loop workera — akceptowalne
   przy jednym kliencie (n8n) i niskim ruchu, ale zaznaczone jawnie jako
   świadomy kompromis, nie przeoczenie.

## Architektura

Dziś `render_paragraph` (`renderer.py`, `docx_renderer.py`) działa tylko
wewnątrz JEDNEGO istniejącego akapitu z szablonu — złamania linii to
`<a:br/>` w tym samym akapicie (świadomie: nowy `<a:p>` powtórzyłby
bullet/numerację/odstępy szablonu). Nagłówki/listy/quote/code-block
wymagają realnych osobnych akapitów o różnym formatowaniu per linia — stąd
zmiana z "podmień tekst w jednym akapicie" na "wygeneruj N akapitów
sklonowanych z formatowania akapitu-szablonu".

Nowy wspólny moduł **`file-renderer-service/richtext.py`** (żeby nie
duplikować logiki między `renderer.py` i `docx_renderer.py`):
- parsuje tekst przez `mistune` (+ 2 własne reguły inline: `<u>`, `~słowo~`)
- zwraca listę **bloków**: `paragraph | heading(level) | bullet_item |
  numbered_item(n) | task_item(checked) | quote | code_block`, każdy z listą
  segmentów runów `(text, {bold, italic, underline, strike, code})` +
  segmenty specjalne `link(text, url)` / `image(alt, url)`
- `fetch_image(url) -> bytes | None` — limity z decyzji #6, `None` przy
  błędzie

Konwencje renderowania bloków (spójne między PPTX i DOCX):
- heading: bold + skala rozmiaru względem fontu z szablonu (h1 ×1.5, h2
  ×1.3, h3 ×1.15)
- listy: prefiks TEKSTOWY na starcie akapitu (`• `, `1. `, `☐ `/`☑ `), NIE
  natywna numeracja OOXML (wymagałaby zdefiniowanego stylu listy w
  konkretnym szablonie, czego nie można założyć)
- quote: kursywa + wcięcie akapitu
- code_block: font monospace na całym akapicie
- link: pptx `run.hyperlink.address`; docx ręczna konstrukcja `w:hyperlink`
  (python-docx nie ma helpera, ale to znana, stabilna technika)
- strike w pptx: ręczny `rPr.set('strike', 'sngStrike')` (python-pptx nie ma
  `font.strike`)

Nowe zależności w `requirements.txt`: `mistune`, `httpx`.

## Fazy implementacji (jedna na raz, deploy + test między nimi)

### Faza 1 — run-level: bold/italic/underline/strike/code-inline/link — ZROBIONE (2026-09-26), czeka na deploy+test
- [x] `richtext.py`: parser mistune + reguły `<u>`/`~słowo~`, segmenty
      run-level (bloki heading/lista/quote/code_block już degradują do
      płaskiego tekstu bez crasha — przygotowane pod Fazę 2, nie w pełnym
      zakresie jeszcze)
- [x] `renderer.py`: `_apply_rich_text` obsługuje bold/italic/underline/
      strike/code/link, `_is_rich`/`_segments` zastąpione `richtext.py`
- [x] `docx_renderer.py`: analogiczna obsługa run-level (wcześniej ZERO
      rich text) + `<br>`/`\n` (czego DOCX też wcześniej nie miał)
- [x] testy: `test_richtext.py` (nowy, 20 przypadków) + rozszerzone
      `test_renderer.py`/`test_docx_renderer.py` (każdy styl + kombinacje +
      hyperlink + regresja białych znaków) — 81/81 zielono
- [ ] deploy + test na żywym szablonie (po stronie usera)

**Napotkane i rozwiązane pułapki (ważne dla Fazy 2/3, żeby nie odkrywać
drugi raz):**
- mistune łączy WSZYSTKIE zarejestrowane reguły inline w jeden wspólny
  regex — `m.group(1)` w callbacku własnej reguły odnosi się do numerowanej
  grupy w TYM połączonym regexie, nie do grupy z własnego wzorca. Poprawnie:
  `m.group(0)` (całe dopasowanie z ogranicznikami) + ręczne cięcie, dokładnie
  jak wbudowane `superscript`/`subscript` w `mistune.plugins.formatting`.
- mistune **ucina białe znaki na brzegach** każdego bloku przed
  parsowaniem inline (`text.strip(" \r\n\t\f")`) — bez obejścia wartość typu
  `"Ala "` traci spację. `richtext.segments()` sam odcina i doklejuje
  spacje/taby z brzegów PRZED wywołaniem mistune, żeby to obejść.
  Dodatkowo: wiodący tab/4+ spacje to w CommonMark "indented code block" —
  ta sama poprawka to też załatwia.
- `<u>...</u>` przychodzi z mistune jako DWA osobne leaf-tokeny
  `inline_html` (otwierający/zamykający), NIE jako zagnieżdżone `children`
  jak `strong`/`emphasis` — trzeba je parować sekwencyjnie podczas
  przechodzenia listy sąsiadów, nie rekurencyjnie.
- Dodano `_coalesce()` (scalanie sąsiednich Spanów o tym samym stylu) —
  bez tego zwykła wartość z końcową spacją (naprawiona wyżej) rozbijałaby
  się na 2 runy zamiast zostać w fast-pathcie `is_rich()==False`.

### Faza 2 — bloki wielowierszowe: heading/listy/task-list/quote/code-block
- [ ] `richtext.py`: rozszerzenie o typy bloków
- [ ] `renderer.py` + `docx_renderer.py`: generowanie N akapitów z
      klonowaniem formatowania akapitu-szablonu
- [ ] testy: heading, każdy typ listy, quote, code block
- [ ] deploy + test na żywym szablonie

### Faza 3 — obrazki
- [ ] `richtext.py`: `fetch_image` z limitami
- [ ] `renderer.py`: obrazek jako osobny shape (best-effort pozycjonowanie)
- [ ] `docx_renderer.py`: obrazek naprawdę inline (`run.add_picture`)
- [ ] testy: fetch z mockiem httpx (bez realnego ruchu sieciowego w
      testach), błąd fetchu → brak crasha i brak obrazka w wyniku
- [ ] deploy + test na żywym szablonie

## Do zaktualizowania po zakończeniu

- README.md (`file-renderer-service/README.md`, sekcja "Ograniczenia",
  linie ~199-207): pełna tabela wspieranej składni, notka o jedynym miejscu
  robiącym zapytania sieciowe + limity.
