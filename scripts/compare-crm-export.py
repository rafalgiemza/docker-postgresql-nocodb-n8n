#!/usr/bin/env python3
"""Porownuje plik wejsciowy starego CRM z eksportem (test pelnego obiegu:
import -> eksport -> porownanie). Czysta analiza plikow, bez bazy.

Usage:  make compare-crm-export ORIG=docs/crm/CRM_big-utf-8.csv EXPORT=docs/crm/export.csv
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "crm-legacy-service"))
import legacy_compare as lc  # noqa: E402
import legacy_import as li  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Porownanie pliku wejsciowego z eksportem")
    ap.add_argument("orig")
    ap.add_argument("export")
    ap.add_argument("--examples", type=int, default=3)
    a = ap.parse_args()
    try:
        res = lc.compare(li.decode(Path(a.orig).read_bytes()),
                         li.decode(Path(a.export).read_bytes()), examples=a.examples)
    except li.LegacyError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    print(lc.render(res))


if __name__ == "__main__":
    main()
