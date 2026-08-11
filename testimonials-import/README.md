# testimonials-import

Jednorazowy kontener-narzędzie, nie serwis (nazwa zostaje historyczna -
pierwotnie tylko dla testimoniali, dziś obsługuje wszystkie importy
"plik od klientki -> tabela NocoDB", bo wszystkie potrzebują tego samego
runtime'u). Daje `python3` + `tesseract-ocr` (+ pakiet językowy polski) +
zależności pythonowe potrzebne przez skrypty w `../scripts/`:

- `import-testimonials.py` — `init-data/source/testimonials.xlsx` →
  tabela `testimonials` + link do `companies` po nazwie firmy.
- `attach-testimonial-slides.py` — `init-data/source/testimonials.pptx` →
  OCR każdego slajdu (to płaskie obrazki, nie tekst), dopasowanie do wiersza
  po imieniu/firmie, wycięcie pojedynczego slajdu i upload do `slide_file`.
- `import-pricing.py` — `init-data/source/cennik.xlsx` → tabela `pricing`
  (UPSERT po strukturze segment/hours/tryb, nie po cenach - bezpieczne
  ponowne uruchomienie po podmianie pliku na wersję z realnymi stawkami).
- `import-packages.py` — `init-data/source/warianty_slajd_4.txt` → tabela
  `package_variants` (parsuje prozaiczny tekst, nie arkusz).

Pełny kontekst i mechanika: nagłówki poszczególnych skryptów.

## Dlaczego kontener, nie `pip install` na hoście

Na Debianie 12 (i nowszym macOS Homebrew) `pip install` poza wirtualnym
środowiskiem kończy się błędem `externally-managed-environment` (PEP 668).
Zamiast venv-a na hoście, zależności (w tym `tesseract-ocr`, którego samego
w sobie nie ma sensu instalować systemowo na cały serwer) siedzą w tym
obrazie.

## Struktura

```
testimonials-import/
├── Dockerfile   - Python 3.12 slim + tesseract-ocr + pip deps
└── README.md    - ta dokumentacja
```

Kod (`../scripts/`) i dane (`../init-data/`) są montowane jako wolumeny
przez `fragments/testimonials-import.yml`, NIE kopiowane do obrazu -
`git pull` działa od razu, rebuild potrzebny tylko po zmianie
`init-data/requirements.txt` albo tego Dockerfile.

## Użycie

Nie startuje z `docker compose up` (ma `profiles: ["tools"]`) - odpalany
punktowo:

```bash
make init-data
# ...albo bezpośrednio, przez wrappery:
./scripts/import-testimonials.sh --dry-run
./scripts/attach-testimonial-slides.sh --dry-run
```

Wymaga `NC_API_TOKEN`/`NC_CRM_BASE_ID` w `.env` (jak reszta stacku) -
`docker compose` czyta `.env` z katalogu repo automatycznie.
