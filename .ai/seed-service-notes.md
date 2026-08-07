# seed-service — notatki operacyjne

## Fragmenty `fragments/*.yml` nie są samodzielne

`fragments/seed-service.yml` (i pozostałe pliki w `fragments/`) są dołączane
przez `include:` w głównym `docker-compose.yml` (patrz `name: docker` na
górze pliku). Nie mają zdefiniowanych zależnych serwisów (np. `nocodb`) —
te żyją w innych fragmentach i łączą się tylko przy starcie z korzenia repo.

Błędne (będzie: `service "seed-service" depends on undefined service "nocodb"`):
```bash
cd old-crm-based-seed/seed-fake
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
