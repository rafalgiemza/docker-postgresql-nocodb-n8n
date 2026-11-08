# crm-legacy-service

Import i eksport historycznych danych CRM **prosto do PostgreSQL**
(schemat `crm`), nie przez NocoDB. Powód: NocoDB nie pozwala ustawić
`created_at`, a zależy nam na prawdziwych datach ze starego CRM
(`.ai/rules/nocodb.md`, sekcja 6).

- `legacy_import.py` — cała logika (parsowanie CSV, mapowanie, SQL). Bez
  zależności poza stdlib; baza jest wstrzykiwana (`db.run(sql, tuples=False)`).
- `legacy_export.py` — eksport do CSV w formacie starego CRM (33 kolumny, daty
  MM/DD/YYYY, UTF-8). Tylko odczyt; odwrotność importu (pola dopisane przez
  import do notatek wracają do swoich kolumn).
- `app.py` — FastAPI: `POST /import?dry_run=&expect_sha256=` (plik CSV jako
  surowe ciało żądania; multipart z n8n się wieszał), `POST /export`, `GET /health`. Woła go tylko n8n (W22 import,
  W23 eksport), brak portów na zewnątrz. Nagłówek `X-Token` = `CRM_LEGACY_TOKEN`.
- CLI (ta sama logika przez `docker exec psql`):
  `make import-crm-legacy CSV=... [APPLY=1]`, `make export-crm-legacy OUT=...`.

## Zasady

- `dry_run=true` wykonuje całość w transakcji i robi ROLLBACK.
- `dry_run=false` wymaga `expect_sha256` zgodnego z plikiem (skrót zwraca
  dry-run) — nie zapiszemy pliku, którego nie sprawdzono (HTTP 409).
- Kolumny pliku dobieramy po NAZWIE nagłówka (kolejność i dodatkowe kolumny nie
  mają znaczenia; nagłówek jedno- lub dwuwierszowy; w zanonimizowanym pliku
  `Kolumna1-3` = osoba/telefon/e-mail). Wymagane: ID, B2B / B2C, Data
  wpłynięcia, Data szansy sprzedaży. Kolumny bez miejsca w CRM (Folder klienta,
  Data archiwizacji) i wartości spoza słowników lub nieczytelne daty trafiają do
  notatek leada ("… (stary CRM): …") - nic nie ginie.
- Idempotencja i numeracja: rejestr `legacy.rows` (schemat `legacy`, poza
  `crm`, więc NocoDB go nie widzi): wiersz Excela (`export_id` = kolumna ID) →
  lead i szansa. Ponowny import pomija ID z rejestru. Sekwencja
  `legacy.export_id_seq` startuje za największym ID z importu - na niej oprzemy
  stabilne ID w eksporcie. `sale_opportunities.legacy_id` też jest wypełniane.
- Brak daty wpłynięcia (większość wierszy pełnego pliku) → data szansy;
  brak daty szansy przy kamieniach milowych → najwcześniejszy kamień.
- Dwie kategorie problemów: (a) da się sensownie zastąpić (brak daty wpłynięcia,
  pusty segment, wartość spoza słownika...) → wiersz jest importowany, ostrzeżenie
  w raporcie; (b) nieczytelna data lub godzina, albo brak jakiejkolwiek daty →
  wiersz jest **pomijany w całości** i wypisany w sekcji "POMINIĘTE WIERSZE" z ID
  i powodem. Po poprawce w pliku trafia do bazy przy następnym imporcie.
- Listy opcji (branża, źródło, forma kontaktu, kwalifikacja) importer czyta z
  NocoDB przez `schema_map.json`. Po dodaniu opcji w NocoDB uruchom
  `make dump-crm-schema` (bez tego użyje wbudowanych słowników i napisze o tym w
  raporcie). Wartość spoza listy nie blokuje wiersza - trafia do notatek.
- Granica "data z przyszłości" przy odczycie M/D vs D/M to dzień importu
  (`export_date` w API, `--export-date` w CLI, domyślnie dziś).
- Raport zbiera ostrzeżenia w grupy ("1376× … (np. #1394, …)").
- Daty zawsze MM/DD/YYYY (wejście i wyjście). Zabezpieczenie na błędy w pliku:
  gdy tak odczytana data jest po dacie eksportu, a DD/MM jest poprawne —
  użyte DD/MM i ostrzeżenie w raporcie.
- Nazwy tabel łączących `_nc_m2m_*` z `docs/archive/fable/schema_map.json`
  (montowany read-only); po zmianie schematu: `make dump-crm-schema`.

## Uruchomienie (raz na środowisko)

1. W `.env`: `CRM_LEGACY_USER`, `CRM_LEGACY_PASSWORD`, `CRM_LEGACY_TOKEN`
   (wzór w `.env.example`).
2. `make grant-crm-legacy` — rola z prawami do `crm` oraz rejestr `legacy.rows`
   (powtórz po dodaniu tabel; bez rejestru import odmówi).
3. `make up` (buduje obraz), potem `make init-schema` (tabele `crm_imports`,
   `crm_exports`).
4. W n8n: credential **Header Auth** „CRM legacy service token”
   (`X-Token` = `CRM_LEGACY_TOKEN`), jego ID do `N8N_CRM_LEGACY_CRED_ID`;
   `make fill-workflows`; import `W22_crm_import.json`.
5. W NocoDB, tabela `crm_imports`: przyciski „Sprawdź import” i „Importuj”
   → akcja *Run Webhook* na `w22-crm-import-check` / `w22-crm-import-apply`.
   Tabela `crm_exports`, przycisk „Eksportuj” → `w23-crm-export`
   (import `W23_crm_export.json`).

## Eksport (kontrakt dla finansow i analizy)

- Kolumna ID = numer z rejestru `legacy.rows`: raz nadany, nigdy nie zmieniany
  ani używany ponownie. Rekordy z nowego CRM dostają kolejny numer z sekwencji
  przy pierwszym eksporcie (eksport zapisuje go w rejestrze), więc kolejne
  eksporty zwracają te same numery. Lead bez szansy, który dostał szansę po
  imporcie, zachowuje swój numer. Usunięty rekord znika z pliku, numer nie wraca.
- Nagłówek i kolejność kolumn = ostatnio zaimportowany plik (`legacy.meta`,
  klucz `header`); handlowiec w zapisie z pliku (`seller:<id>`). Bez importu:
  układ klienta (33 kolumny).
- Formaty jak w pliku źródłowym: daty M/D/YYYY (bez zer), `H:MM:SS AM/PM`,
  kwoty `3,900.00 PLN`, UTF-8 z BOM, CRLF, od najwyższego ID. Komórki puste w
  pliku źródłowym (np. data wpłynięcia, dane osobowe zastępcze) wracają puste.
- Wartości, których import nie umiał zapisać (spoza słowników, nieczytelne
  daty, Folder klienta, Data archiwizacji, kwota przy leadzie bez szansy) wracają
  z notatek do swoich kolumn.
- Test pełnego obiegu: `make export-crm-legacy OUT=…` potem
  `make compare-crm-export ORIG=<plik> EXPORT=<eksport>` - porównanie po
  znaczeniu (ta sama data/kwota w innym zapisie to nie różnica). Na pliku
  `CRM_big-utf-8.csv`: 1684 z 1686 wierszy identyczne; różnice: pusty segment
  → B2C (#1473) i `Email` → `Mail`; #1585 (bez dat) nie jest importowany.
- Daty kamieni milowych są zachowane dokładnie, także gdy w pliku są
  niespójne (np. podpisanie przed wysłaniem umowy) - import zgłasza je w raporcie.

## Testy

```
cd crm-legacy-service && python3 -m pytest test_legacy_import.py
```

## Tryb „anonim"

Pole `anonymous` (checkbox) w `crm_imports` → parametr `anonymous=true` w `/import`
(CLI: `--anonymous`). Importer traktuje wtedy kolumny osobowe jak puste: osoba
kontaktowa, telefon, e-mail oraz nazwa klienta/organizacja dla B2C (B2B zostaje z
nazwą firmy). Powstają placeholdery `Nieznany kontakt (stary CRM #ID)`, które eksport
zamienia z powrotem na puste komórki. Skrót pliku zależy od trybu, więc „Importuj"
działa tylko w tym samym trybie, w którym zrobiono „Sprawdź import". Notatki i
„Folder klienta" są przepisywane bez zmian.
