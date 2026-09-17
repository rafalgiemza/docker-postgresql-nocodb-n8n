#!/usr/bin/env python3
r"""Wypełnia `package_variants_cores`/`package_variants_adons` z
`init-data/warianty_core.txt`/`init-data/warianty_adons.txt`.

Zmiana 2026-09-17: klientka dostarczyła osobne pliki dla dwóch katalogów
(patrz nagłówek scripts/init-schema.py "Zmiana z 2026-09-16"/"z 2026-09-17")
zamiast jednego `warianty_slajd_4.txt` (usunięty - 10 pakietów podzielone
na 2 core + 8 adons). Ten skrypt importuje OBA pliki w jednym przebiegu
(`--catalog` pozwala ograniczyć do jednego), każdy do swojego katalogu:
- `warianty_core.txt` -> `package_variants_cores` (GŁÓWNE pakiety)
- `warianty_adons.txt` -> `package_variants_adons` (dodatki/skille)

Format obu plików identyczny - prozaiczna lista dla slajdu "NASZA
REKOMENDACJA" (dostarczona przez klientkę), naprzemiennie: linia z nazwą
pakietu (zaczyna się od "✅", zawiera placeholdery {{package.hours}} itd.,
które i tak nie są tu parsowane - trafiają do oferty dopiero w n8n) i linia
z krótkim opisem. Parser niżej rozbija ją na pary (name, description).

`package_variants_adons.default_hours`/`.key` NIE występują w
`warianty_adons.txt` - zostają puste, do ręcznego uzupełnienia w NocoDB po
imporcie (analogicznie do `package_variants_cores.slides`, które i tak
trzeba dopiąć osobno przez `package_core_slides`).

Uwaga na duplikaty nazw: `warianty_adons.txt` ma DWA wpisy "English +
Business Skills: Facilitating" i DWA "...Negotiating" - każdy z INNYM
opisem (dwa warianty tekstu marketingowego, prawdopodobnie pod różne
konteksty/odbiorców) - to świadomie zostaje jako dwa osobne wiersze, `name`
nie jest unikalne. Dedupe (klucz: fold(name)+fold(description)) chroni
tylko przed powtórnym uruchomieniem tego samego pliku, nie przed tym
zamierzonym duplikatem nazwy.

Idempotentny: dedupe po kluczu naturalnym fold(name)+fold(description),
bez osobnego pola legacy_id - jak import-testimonials.py.

Wymaga w środowisku (patrz .env.example): NC_API_TOKEN, NC_CRM_BASE_ID.
Opcjonalnie: NC_LOCAL_URL (default http://localhost:8081).

Usage (przez kontener testimonials-import - patrz jego README, PEP 668 na
hoście robi z gołego `pip install` problem):
  ./scripts/import-packages.sh --dry-run       # ZAWSZE najpierw, oba katalogi
  ./scripts/import-packages.sh                 # oba katalogi
  ./scripts/import-packages.sh --catalog adons  # tylko dodatki
  ./scripts/import-packages.sh --catalog cores --txt inny/plik.txt
"""
import argparse
import os
import sys
import unicodedata
from collections import defaultdict

import requests

URL = os.environ.get("NC_LOCAL_URL", "http://localhost:8081").rstrip("/")
TOKEN = os.environ.get("NC_API_TOKEN")
BASE_ID = os.environ.get("NC_CRM_BASE_ID")
BULLET = "✅"
DASH = "–"  # en dash - separator w "✅ Nazwa – reszta" w źródłowym pliku

CATALOGS = {
    "cores": {"txt": "init-data/warianty_core.txt", "table": "package_variants_cores"},
    "adons": {"txt": "init-data/warianty_adons.txt", "table": "package_variants_adons"},
}

if not TOKEN or not BASE_ID:
    sys.exit("Brak NC_API_TOKEN / NC_CRM_BASE_ID w środowisku - patrz .env.example.")

S = requests.Session()
S.headers.update({"xc-token": TOKEN, "Content-Type": "application/json"})


def api(method, path, **kw):
    try:
        r = S.request(method, f"{URL}{path}", timeout=30, **kw)
    except requests.RequestException as e:
        sys.exit(f"Nie moge sie polaczyc z NocoDB ({URL}): {type(e).__name__}. "
                 f"Sprawdz NC_LOCAL_URL / czy kontener stoi.")
    if not r.ok:
        sys.exit(f"NocoDB API error {r.status_code} on {method} {path}: {r.text[:500]}")
    return r.json() if r.text else {}


def fold(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore") \
        .decode().lower().strip()
    return s.strip(" -,.")


# ----------------------------------------------------------------- meta
def resolve_table(tables_by_title, table_title):
    if table_title not in tables_by_title:
        sys.exit(f"Brak tabeli `{table_title}` (uruchom najpierw `make init-schema`).")
    return tables_by_title[table_title]


def existing_keys(tid):
    rows = api("GET", f"/api/v2/tables/{tid}/records?limit=1000").get("list", [])
    return {(fold(r.get("name")), fold(r.get("description"))) for r in rows}


# ----------------------------------------------------------------- txt
def load_pairs(path):
    with open(path, encoding="utf-8-sig") as f:
        lines = [ln.strip() for ln in f if ln.strip()]

    # pierwsza linia to nagłówek opisowy pliku, nie pakiet - pomiń wszystko
    # przed pierwszą linią zaczynającą się od BULLET
    start = next((i for i, ln in enumerate(lines) if ln.startswith(BULLET)), None)
    if start is None:
        sys.exit(f"Nie znalazłem żadnej linii zaczynającej się od {BULLET!r} w {path}.")
    body = lines[start:]

    if len(body) % 2 != 0:
        sys.exit(f"Nieparzysta liczba linii pakietów w {path} ({len(body)}) - "
                 f"każdy pakiet musi mieć linię z nazwą i linię z opisem. "
                 f"Ostatnia linia: {body[-1]!r}")

    pairs = []
    for i in range(0, len(body), 2):
        name_line, desc_line = body[i], body[i + 1]
        if not name_line.startswith(BULLET):
            sys.exit(f"Oczekiwałem linii z nazwą pakietu (zaczyna się od {BULLET!r}), "
                     f"dostałem: {name_line!r}")
        if desc_line.startswith(BULLET):
            sys.exit(f"Brak linii opisu po nazwie {name_line!r} - kolejna linia to "
                     f"znowu nazwa pakietu: {desc_line!r}")
        raw = name_line[len(BULLET):].strip()
        if DASH not in raw:
            sys.exit(f"Linia nazwy bez separatora {DASH!r}: {name_line!r}")
        name = raw.split(DASH, 1)[0].strip()
        pairs.append((name, desc_line))
    return pairs


# ----------------------------------------------------------------- import
def import_catalog(tables_by_title, catalog_name, txt_path, table_title, dry_run):
    print(f"\n--- {catalog_name}: {txt_path} -> {table_title} ---")
    if not os.path.exists(txt_path):
        sys.exit(f"Nie znaleziono pliku: {txt_path}")

    tid = resolve_table(tables_by_title, table_title)
    pairs = load_pairs(txt_path)
    print(f"Pakiety w pliku: {len(pairs)}")

    existing = existing_keys(tid)
    stats = defaultdict(int)
    seen_this_run = set()

    for name, description in pairs:
        stats["rows_read"] += 1
        key = (fold(name), fold(description))
        if key in existing or key in seen_this_run:
            stats["skipped_duplicate"] += 1
            continue
        seen_this_run.add(key)

        record = {"name": name, "description": description}
        print(f"+  {name!r} -> {description[:60]!r}...")
        stats["created"] += 1
        if dry_run:
            continue
        api("POST", f"/api/v2/tables/{tid}/records", json=record)

    print(f"----- {catalog_name}: " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))
    return stats


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--catalog", choices=[*CATALOGS, "all"], default="all",
                     help="Który katalog zaimportować (domyślnie: all = oba).")
    ap.add_argument("--txt", help="Nadpisz domyślną ścieżkę pliku źródłowego "
                                   "(tylko razem z --catalog cores|adons).")
    args = ap.parse_args()

    if args.txt and args.catalog == "all":
        sys.exit("--txt wymaga --catalog cores|adons (nie all - nie da się "
                 "nadpisać ścieżki dla dwóch katalogów naraz).")

    print(f"NocoDB: {URL}, base: {BASE_ID}{' [DRY RUN]' if args.dry_run else ''}")

    tables_by_title = {t["title"].strip().lower(): t["id"]
                        for t in api("GET", f"/api/v2/meta/bases/{BASE_ID}/tables").get("list", [])}

    targets = CATALOGS if args.catalog == "all" else {args.catalog: CATALOGS[args.catalog]}
    total = defaultdict(int)
    for catalog_name, cfg in targets.items():
        stats = import_catalog(tables_by_title, catalog_name,
                                args.txt or cfg["txt"], cfg["table"], args.dry_run)
        for k, v in stats.items():
            total[k] += v

    print("\n===== REPORT (razem) =====")
    for k, v in sorted(total.items()):
        print(f"{k}: {v}")
    if args.dry_run:
        print("\n(dry run - nic nie zapisano)")


if __name__ == "__main__":
    main()
