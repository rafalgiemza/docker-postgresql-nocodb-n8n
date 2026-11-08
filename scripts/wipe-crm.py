#!/usr/bin/env python3
"""Czysci WSZYSTKIE tabele schematu crm POZA wskazanymi (domyslnie: employees).

Przed produkcyjnym wgraniem prawdziwych danych. Obejmuje tez tabele laczace
NocoDB (_nc_m2m_*) i slowniki/katalogi (pricing, szablony...) - podglad
pokazuje liczby wierszy, a `--keep` dodaje kolejne tabele do zachowania.
Domyslnie PODGLAD (transakcja z ROLLBACK); sekwencje (ID) zerowane.
Nie uzywa CASCADE, wiec employees nie zostanie ruszone; jesli employees ma FK
do czyszczonej tabeli, baza odmowi (dodaj te tabele do --keep).

Usage:  make wipe-crm                         # podglad
        make wipe-crm KEEP="pricing"          # zachowaj tez pricing
        make wipe-crm ONLY="leads persons"    # tylko te (+ ich tabele laczace)
        make wipe-crm APPLY=1                 # czysci
"""
import argparse
import importlib.util
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
    ap = argparse.ArgumentParser(description="Wyczysc crm poza wybranymi tabelami")
    ap.add_argument("--apply", action="store_true", help="COMMIT (domyslnie podglad)")
    ap.add_argument("--keep", nargs="*", default=[], help="dodatkowe tabele do zachowania")
    ap.add_argument("--only", nargs="*", default=None,
                    help="czysc TYLKO te tabele (+ tabele laczace _nc_m2m_* z kluczem obcym do nich)")
    ap.add_argument("--container", default=os.environ.get("PG_CONTAINER", "docker-postgres-1"))
    ap.add_argument("--user", default=os.environ.get("POSTGRES_USER", "postgres"))
    ap.add_argument("--db", default=os.environ.get("APP_DB", "appdata"))
    a = ap.parse_args()
    keep = {"employees", *a.keep}
    db = cli.DockerPg(a.container, a.user, a.db)
    try:
        tables = [r[0] for r in db.run(
            f"SELECT tablename FROM pg_tables WHERE schemaname='{li.SCHEMA}' ORDER BY 1",
            tuples=True)]
        missing = keep - set(tables)
        if missing:
            raise li.LegacyError(f"Brak tabel do zachowania: {sorted(missing)}")
        if a.only is not None:
            unknown = set(a.only) - set(tables)
            if unknown:
                raise li.LegacyError(f"Brak tabel: {sorted(unknown)}")
            wipe = set(a.only)
            # tabele laczace NocoDB z FK do czyszczonej tabeli musza zniknac razem z nia
            # (inaczej baza odmowi, albo zostalyby osierocone relacje)
            for t, _, ref in lc._refs(db):
                if t.startswith(lc.JUNCTION_PREFIX) and ref in wipe:
                    wipe.add(t)
            keep = set(tables) - wipe
            wipe = [t for t in tables if t in wipe]
        else:
            wipe = [t for t in tables if t not in keep]
        counts = {t: db.run(f"SELECT count(*) FROM {li.SCHEMA}.{li.ident(t)}", tuples=True)[0][0]
                  for t in tables}
        print(f"Baza: {a.db}   zachowane: {', '.join(sorted(keep))}")
        for t in wipe:
            print(f"  czyszczone  {t:45} {counts[t]:>6}")
        for t in sorted(keep):
            print(f"  ZACHOWANE   {t:45} {counts[t]:>6}")
        lst = ", ".join(f"{li.SCHEMA}.{li.ident(t)}" for t in wipe)
        reg = db.run("SELECT to_regclass('legacy.rows')", tuples=True)
        reset_registry = bool(reg and reg[0] and reg[0][0]) and (
            "leads" in wipe or "sale_opportunities" in wipe)
        if reset_registry:  # inaczej import uznalby wiersze za juz zaimportowane
            n = db.run("SELECT count(*) FROM legacy.rows", tuples=True)[0][0]
            print(f"  czyszczone  {'legacy.rows (rejestr ID importu)':45} {n:>6}")
        db.run(f"BEGIN;\nTRUNCATE {lst} RESTART IDENTITY;\n"
               + ("TRUNCATE legacy.rows;\nALTER SEQUENCE legacy.export_id_seq RESTART;\n"
                  if reset_registry else "")
               + f"{'COMMIT' if a.apply else 'ROLLBACK'};")
    except li.LegacyError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    print("✅ WYCZYSZCZONO (COMMIT)" if a.apply else
          "🧪 PODGLĄD: nic nie usunięto. Powtórz z APPLY=1.")


if __name__ == "__main__":
    main()
