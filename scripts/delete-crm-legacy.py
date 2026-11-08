#!/usr/bin/env python3
"""Usuwa z bazy rekordy dodane przez import (zakres ID z pliku), zeby moc
zaimportowac poprawiony plik od nowa. Domyslnie PODGLAD (transakcja z ROLLBACK).
Logika: crm-legacy-service/legacy_cleanup.py.

Usage:  make delete-crm-legacy IDS=1704-1713            # podglad
        make delete-crm-legacy IDS=1704-1713 APPLY=1    # kasuje
"""
import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "crm-legacy-service"))
import legacy_cleanup as lc  # noqa: E402
import legacy_import as li  # noqa: E402

spec = importlib.util.spec_from_file_location("import_cli", HERE / "import-crm-legacy.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def main():
    ap = argparse.ArgumentParser(description="Usun zaimportowane rekordy")
    ap.add_argument("ids", help="zakres ID z pliku, np. 1704-1713")
    ap.add_argument("--apply", action="store_true", help="COMMIT (domyslnie podglad)")
    ap.add_argument("--container", default=os.environ.get("PG_CONTAINER", "docker-postgres-1"))
    ap.add_argument("--user", default=os.environ.get("POSTGRES_USER", "postgres"))
    ap.add_argument("--db", default=os.environ.get("APP_DB", "appdata"))
    ap.add_argument("--schema-map", default="docs/archive/fable/schema_map.json")
    a = ap.parse_args()
    with open(a.schema_map, encoding="utf-8") as f:
        schema_map = json.load(f)
    try:
        lo, hi = lc.parse_range(a.ids)
        res = lc.run_cleanup(cli.DockerPg(a.container, a.user, a.db), schema_map, lo, hi, a.apply)
    except li.LegacyError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    print(res["counts"])
    print("✅ USUNIĘTO (COMMIT)" if a.apply else
          "🧪 PODGLĄD: nic nie usunięto. Powtórz z --apply (make ... APPLY=1).")


if __name__ == "__main__":
    main()
