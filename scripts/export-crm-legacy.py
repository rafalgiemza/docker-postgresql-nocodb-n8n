#!/usr/bin/env python3
"""Eksport CRM z PostgreSQL do pliku CSV w formacie starego CRM (33 kolumny,
daty MM/DD/YYYY, UTF-8). Cienki CLI nad crm-legacy-service/legacy_export.py;
tylko odczyt. Patrz .ai/rules/nocodb.md, sekcja 6.

Usage:  make export-crm-legacy OUT=docs/crm/export.csv
"""
import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "crm-legacy-service"))
import legacy_export as le  # noqa: E402
import legacy_import as li  # noqa: E402

spec = importlib.util.spec_from_file_location("import_cli", HERE / "import-crm-legacy.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def main():
    ap = argparse.ArgumentParser(description="Eksport CRM do CSV")
    ap.add_argument("out")
    ap.add_argument("--container", default=os.environ.get("PG_CONTAINER", "docker-postgres-1"))
    ap.add_argument("--user", default=os.environ.get("POSTGRES_USER", "postgres"))
    ap.add_argument("--db", default=os.environ.get("APP_DB", "appdata"))
    ap.add_argument("--schema-map", default="docs/archive/fable/schema_map.json")
    a = ap.parse_args()
    with open(a.schema_map, encoding="utf-8") as f:
        schema_map = json.load(f)
    try:
        data, n = le.run_export(cli.DockerPg(a.container, a.user, a.db), schema_map)
    except li.LegacyError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    Path(a.out).write_bytes(data)
    print(f"✅ {n} wierszy -> {a.out}")


if __name__ == "__main__":
    main()
