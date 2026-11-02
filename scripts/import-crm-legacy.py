#!/usr/bin/env python3
"""Import historycznych rekordow ze starego CRM (CSV) wprost do PostgreSQL.

Cienki CLI nad crm-legacy-service/legacy_import.py (ta sama logika co
serwis HTTP wolany z n8n).

WYJATEK OD ZASADY "dane przez NocoDB": NocoDB nie pozwala ustawic created_at,
a tu zalezy nam na prawdziwych datach (wplyniecie leada, utworzenie klienta,
kamienie milowe szansy). Decyzja: .ai/rules/nocodb.md, sekcja 6.

Odpowiednik W4v4 (docs/archive/fable/W4v4_form_intake.json) dla rekordow
historycznych. Z jednego wiersza CSV powstaja:
  - company (tylko B2B; dedup po nazwie),
  - person (dedup po e-mailu, potem po 9 ostatnich cyfrach telefonu),
  - lead (legacy_id = ID ze starego CRM; to klucz idempotencji),
  - linki: leads.persons (M2M), leads.primary_person, leads.owner,
    leads.company, persons.company,
  - activity `lead_created`,
  - sale_opportunity + sale_opportunity_stage_history, gdy w wierszu jest
    "Data szansy sprzedazy" (bez niej wiersz to sam lead - utrata/powod
    laduja w notatkach leada).
Nie uruchamia zadnych flow n8n/NocoDB (brak W2, W20, zadan), dlatego historie
etapow zapisujemy sami.

Linki (leads.company, leads.owner, leads.persons...) w schemacie v4 siedza w
tabelach laczacych `_nc_m2m_*`: ich nazwy bierzemy z schema_map.json, a nazwy
kolumn z kluczy obcych w information_schema (nic nie jest zgadywane; brak FK =
blad z prosba o `\\d`). Gdy tabeli laczacej nie ma, uzywamy zwyklej kolumny FK.

Usage (z korzenia repo, .env wczytany przez make albo zmienne w srodowisku):
  ./scripts/import-crm-legacy.sh docs/crm/crm-utf-8.csv            # DRY-RUN
  ./scripts/import-crm-legacy.sh docs/crm/crm-utf-8.csv --apply    # zapis
Dry-run wykonuje CALOSC w transakcji i ja wycofuje (ROLLBACK), wiec
wychwytuje tez bledy ograniczen bazy. --apply robi COMMIT.

Daty w CSV: MM/DD/YYYY. Jesli tak odczytana data jest pozniejsza niz data
eksportu (--export-date), a odczyt DD/MM jest poprawny i nie pozniejszy,
uzywamy DD/MM (np. 12/10/2026 -> 12 pazdziernika). Kazda zamiana jest
logowana. Godzina wplyniecia: Europe/Warsaw; brak godziny = 00:00, pozostale
daty bez godziny = 12:00 (nie wczesniej niz wplyniecie leada).
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "crm-legacy-service"))
import legacy_import as li  # noqa: E402


class DockerPg:
    """Interfejs bazy przez `docker exec <kontener> psql` (stdlib, bez psycopg)."""

    def __init__(self, container, user, db):
        self.cmd = ["docker", "exec", "-i", container, "psql", "-U", user,
                    "-d", db, "-X", "-v", "ON_ERROR_STOP=1"]

    def run(self, sql, tuples=False):
        cmd = self.cmd + (["-A", "-t", "-F", "\t"] if tuples else [])
        p = subprocess.run(cmd, input=sql, capture_output=True, text=True)
        if p.returncode != 0:
            raise li.LegacyError(f"psql: {p.stderr.strip() or p.stdout.strip()}")
        if tuples:
            return [ln.split("\t") for ln in p.stdout.splitlines() if ln]
        return p.stdout + p.stderr


def main():
    ap = argparse.ArgumentParser(description="Import starego CRM (CSV) do Postgresa")
    ap.add_argument("csv")
    ap.add_argument("--apply", action="store_true",
                    help="COMMIT (domyslnie dry-run = ROLLBACK)")
    ap.add_argument("--export-date", default="2026-10-30",
                    help="data eksportu CSV (YYYY-MM-DD)")
    ap.add_argument("--container", default=os.environ.get("PG_CONTAINER", "docker-postgres-1"))
    ap.add_argument("--user", default=os.environ.get("POSTGRES_USER", "postgres"))
    ap.add_argument("--db", default=os.environ.get("APP_DB", "appdata"))
    ap.add_argument("--schema-map", default="docs/archive/fable/schema_map.json",
                    help="dump z `make dump-crm-schema` (nazwy tabel laczacych)")
    ap.add_argument("--sql-out", help="zapisz wygenerowany SQL do pliku (podglad)")
    a = ap.parse_args()

    with open(a.schema_map, encoding="utf-8") as f:
        schema_map = json.load(f)
    with open(a.csv, "rb") as f:
        data = f.read()
    try:
        res = li.run_import(DockerPg(a.container, a.user, a.db), data, schema_map,
                            apply=a.apply, export_date=date.fromisoformat(a.export_date),
                            sql_out=a.sql_out)
    except li.LegacyError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    for w in res["warnings"]:
        print(f"⚠️  {w}")
    print(f"📄 wiersze: {res['rows']}, wynik: {res['counts']}")
    print(("✅ ZAPISANO (COMMIT)" if a.apply else
           "🧪 DRY-RUN: transakcja wycofana. Powtorz z --apply, by zapisac.")
          + f" Ostrzezen: {len(res['warnings'])}. sha256={res['sha256'][:12]}")


if __name__ == "__main__":
    main()
