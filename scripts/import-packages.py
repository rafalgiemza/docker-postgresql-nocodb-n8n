#!/usr/bin/env python3
r"""Wypełnia `package_variants` z `init-data/source/warianty_slajd_4.txt`.

Plik NIE jest tabelą - to prozaiczna lista dla slajdu "NASZA REKOMENDACJA"
(dostarczona przez klientkę 2026-08-11), naprzemiennie: linia z nazwą
pakietu (zaczyna się od "✅", zawiera placeholdery {{package.hours}} itd.,
które i tak nie są tu parsowane - trafiają do oferty dopiero w n8n) i linia
z krótkim opisem. Parser niżej rozbija ją na pary (name, short_description).

`lesson_frequency`/`lesson_minutes` NIE występują w tym pliku (tylko jako
placeholdery {{lessonfrequency}}/{{lesson.minutes}} w tekście nazwy, bez
wartości) - zostają puste, do ręcznego uzupełnienia w NocoDB po imporcie.

Uwaga na duplikaty nazw: część pakietów (np. "English + Business Skills:
Facilitating") występuje w pliku DWA razy z INNYM opisem (dwa warianty
tekstu marketingowego, prawdopodobnie pod różne konteksty/odbiorców) - to
świadomie zostaje jako dwa osobne wiersze, `name` na `package_variants` nie
jest unikalne. Dedupe (klucz: fold(name)+fold(short_description)) chroni
tylko przed powtórnym uruchomieniem tego samego pliku, nie przed tym
zamierzonym duplikatem nazwy.

Idempotentny: dedupe po kluczu naturalnym fold(name)+fold(short_description),
bez osobnego pola legacy_id - jak import-testimonials.py.

Wymaga w środowisku (patrz .env.example): NC_API_TOKEN, NC_CRM_BASE_ID.
Opcjonalnie: NC_LOCAL_URL (default http://localhost:8081).

Usage (przez kontener testimonials-import - patrz jego README, PEP 668 na
hoście robi z gołego `pip install` problem):
  ./scripts/import-packages.sh --dry-run   # ZAWSZE najpierw
  ./scripts/import-packages.sh [--txt PATH]
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
DEFAULT_TXT = "init-data/source/warianty_slajd_4.txt"
BULLET = "✅"
DASH = "–"  # en dash - separator w "✅ Nazwa – reszta" w źródłowym pliku

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
def resolve_meta():
    tables = {t["title"].strip().lower(): t["id"]
              for t in api("GET", f"/api/v2/meta/bases/{BASE_ID}/tables").get("list", [])}
    if "package_variants" not in tables:
        sys.exit("Brak tabeli `package_variants` (uruchom najpierw `make init-schema`).")
    return tables["package_variants"]


def existing_keys(tid):
    rows = api("GET", f"/api/v2/tables/{tid}/records?limit=1000").get("list", [])
    return {(fold(r.get("name")), fold(r.get("short_description"))) for r in rows}


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


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--txt", default=DEFAULT_TXT)
    args = ap.parse_args()

    print(f"NocoDB: {URL}, base: {BASE_ID}{' [DRY RUN]' if args.dry_run else ''}")
    if not os.path.exists(args.txt):
        sys.exit(f"Nie znaleziono pliku: {args.txt}")

    tid = resolve_meta()
    pairs = load_pairs(args.txt)
    print(f"Pakiety w pliku: {len(pairs)}")

    existing = existing_keys(tid)
    stats = defaultdict(int)
    seen_this_run = set()

    for name, short_description in pairs:
        stats["rows_read"] += 1
        key = (fold(name), fold(short_description))
        if key in existing or key in seen_this_run:
            stats["skipped_duplicate"] += 1
            continue
        seen_this_run.add(key)

        record = {"name": name, "short_description": short_description, "active": True}
        print(f"+  {name!r} -> {short_description[:60]!r}...")
        stats["created"] += 1
        if args.dry_run:
            continue
        api("POST", f"/api/v2/tables/{tid}/records", json=record)

    print("\n===== REPORT =====")
    for k, v in sorted(stats.items()):
        print(f"{k}: {v}")
    if args.dry_run:
        print("\n(dry run - nic nie zapisano)")


if __name__ == "__main__":
    main()
