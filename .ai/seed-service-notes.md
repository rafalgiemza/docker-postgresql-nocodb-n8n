# seed-service — notatki operacyjne

## Fragmenty `fragments/*.yml` nie są samodzielne

`fragments/seed-service.yml` (i pozostałe pliki w `fragments/`) są dołączane
przez `include:` w głównym `docker-compose.yml` (patrz `name: docker` na
górze pliku). Nie mają zdefiniowanych zależnych serwisów (np. `nocodb`) —
te żyją w innych fragmentach i łączą się tylko przy starcie z korzenia repo.

Błędne (będzie: `service "seed-service" depends on undefined service "nocodb"`):
```bash
cd init-data
docker compose -f fragments/seed-service.yml build seed-service
```

Poprawne — zawsze z katalogu z `docker-compose.yml` (na VPS: `~/coaction-test`):
```bash
cd ~/coaction-test
docker compose build seed-service
docker compose up -d seed-service
curl http://localhost:8001/preview?limit=10
```

## Bug: `EXCEL_PATH` niezdefiniowane (naprawiony 2026-08-07)

`seed_app.py` definiował stałą jako `DEFAULT_EXCEL_PATH`, ale `read_excel()`
odwoływał się do nieistniejącej `EXCEL_PATH` → `NameError` przy
`GET /preview` i `/seed`. Poprawka: `read_excel()` używa teraz
`DEFAULT_EXCEL_PATH` (zgodnie z resztą pliku, np. `/health`).

Po zmianach w `seed_app.py` obraz trzeba przebudować — kod jest kopiowany
do obrazu w `Dockerfile` (`COPY seed_app.py .`), nie montowany jako wolumen.

## CLI seeder usunięty (2026-08-07)

`init-data/seed_nocodb_from_excel.py` +
`SEED_EXCEL_README.md` zostały usunięte — zdублowany odpowiednik
`seed-service` (Docker/FastAPI), ale utrzymywany osobno od migracji
schematu w `docs/archive/fable/feedback-tables-1.md` (2026-08-06). W efekcie CLI miał
aktualne nazwy pól (`lead_name`/`lead_type`/`lead_source`/`deal_value`,
mapowania `SOURCE_MAP`/`CHANNEL_MAP`/`INDUSTRY_MAP` pod nową listę opcji,
`LOSS_REASON_MAP`, zapis niezmapowanych wartości do `notes`), a
`seed_app.py` miał stare (`contact_name`/`type`/`source`/`value`, stare
mapowania bez fallbacku do `notes`) — dwa niezgodne ze sobą seedery.

Przed usunięciem CLI-a przeniesiono jego aktualną logikę mapowań do
`seed_app.py` (funkcja `build_lead_data()` + zaktualizowane mapy stałych),
więc `seed-service` jest teraz jedynym i aktualnym sposobem seedowania.
Przy okazji wydzielono współdzieloną `seed_records()` używaną przez
`/seed` i `/seed-upload` zamiast dwóch kopii tej samej logiki (przyczyna
rozjazdu na przyszłość — jedna kopia = jedno miejsce do aktualizacji przy
kolejnej zmianie schematu).
