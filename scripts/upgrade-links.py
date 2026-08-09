#!/usr/bin/env python3
r"""Upgraduje pola relacji CRM (RELATIONS z init-schema.py) ze starego
formatu "Link to another record" v1 (Links/LinkToAnotherRecord bez fizycznej
tabeli łączącej dla relacji hm) do v3 (LinkToAnotherRecord + fizyczna tabela
łącząca `_nc_m2m_*`) przez NocoDB Meta API.

To jest automatyzacja punktu "WYMAGA RĘCZNEGO DOKOŃCZENIA" z nagłówka
init-schema.py: krok DRUGI, PO `make init-schema` (pola relacji muszą już
istnieć).

CO FAKTYCZNIE ROBI "UPGRADE" W UI — zweryfikowane w źródle NocoDB
(packages/nc-gui/components/dlg/ConvertLinkV2.vue,
packages/nocodb/src/services/columns.service.ts:
convertLinkToV2/convertMMToV2, 2026-08 `nocodb/nocodb` @ `master`):

Klik "Upgrade" -> accept -> save w dialogu to JEDNO wywołanie:
  POST /api/v2/internal/{workspaceId}/{baseId}
       ?operation=convertLinkToV2&columnId={columnId}
które atomowo (transakcja + realne DDL na zewnętrznym źródle appdata):
  - tworzy fizyczną tabelę łączącą (_nc_m2m_*) i migruje do niej dane
    z kolumny FK,
  - kasuje legacy kolumnę FK z appdata (dla relacji hm/bt),
  - po stronie pola, które stworzył nasz init-schema.py (uidt=Links):
    konwertuje JE W MIEJSCU na Rollup (od teraz pokazuje tylko licznik,
    zachowuje tytuł) i TWORZY NOWE pole "LTAR_<tytuł>" (uidt=
    LinkToAnotherRecord) z prawdziwą relacją,
  - po stronie sparowanej (auto-pole zwrotne, którego nazwy init-schema.py
    i tak nie kontroluje) po prostu przełącza uidt Links -> LinkToAnotherRecord
    w miejscu, bez nowego pola - nie wymaga akcji z naszej strony.

Stąd ręczne kroki obserwowane w UI: klik "Upgrade" (= powyższy jeden
request), usuń stare pole (teraz Rollup, ten sam tytuł co przed upgrade'em),
zmień nazwę "LTAR_<tytuł>" na oryginalny tytuł. Ten skrypt robi dokładnie to,
per relacja z RELATIONS (importowane z init-schema.py, żeby nie duplikować
listy - patrz `_spec` niżej):
  1. POST convertLinkToV2 na kolumnie z RELATIONS (o ile jeszcze uidt=Links),
  2. DELETE starego pola (teraz Rollup, tytuł = oryginalny),
  3. PATCH nowego pola "LTAR_<tytuł>" -> tytuł = oryginalny.

Idempotentny i wznawialny: rozpoznaje aktualny etap każdej relacji po uidt
(Links = jeszcze nic nie zrobione, Rollup+LTAR_* = przerwane w połowie,
LinkToAnotherRecord = już gotowe) i robi tylko brakującą resztę. Bezpieczne
do wielokrotnego uruchomienia.

UWAGA: to prawdziwe DDL na appdata (nowa tabela `_nc_m2m_*`, DROP starej
kolumny FK), nie tylko metadane NocoDB. Zrób `make backup` przed pierwszym
uruchomieniem na produkcji.

Wymaga w środowisku (patrz .env.example): NC_API_TOKEN, NC_CRM_BASE_ID.
Opcjonalnie NC_LOCAL_URL (domyślnie http://localhost:8081).

Usage:
  make upgrade-links
  # albo bezpośrednio:
  set -a; source .env; set +a
  python3 scripts/upgrade-links.py --dry-run
  python3 scripts/upgrade-links.py
"""
import argparse
import importlib.util
from pathlib import Path

# Import init-schema.py jako moduł (nazwa pliku ma myślnik, stąd loader po
# ścieżce, nie zwykły `import`). Kod tworzący tabele/relacje jest pod
# `if __name__ == "__main__":`, więc samo wczytanie modułu nie odpala
# żadnych wywołań API - dostajemy tylko RELATIONS/api/table_columns/S.
_spec = importlib.util.spec_from_file_location(
    "init_schema", Path(__file__).parent / "init-schema.py"
)
init_schema = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(init_schema)

api = init_schema.api
URL = init_schema.URL
BASE_ID = init_schema.BASE_ID
RELATIONS = init_schema.RELATIONS
existing_tables = init_schema.existing_tables
table_columns = init_schema.table_columns


def resolve_workspace_id():
    return api("GET", f"/api/v2/meta/bases/{BASE_ID}")["fk_workspace_id"]


def convert_link_to_v2(workspace_id, column_id):
    api(
        "POST",
        f"/api/v2/internal/{workspace_id}/{BASE_ID}"
        f"?operation=convertLinkToV2&columnId={column_id}",
        json={},
    )


def rename_column(column_id, new_title):
    # PATCH oczekuje całego obiektu pola, nie tylko zmienianych kluczy -
    # columnUpdate po stronie NocoDB porównuje przesłany `uidt` ze starym
    # przy decyzji "czy to zmiana typu", więc częściowy PATCH (bez uidt)
    # ryzykuje fałszywe wykrycie zmiany typu. Pobieramy pełny obiekt i
    # zmieniamy tylko tytuł.
    col = api("GET", f"/api/v2/meta/columns/{column_id}")
    col["title"] = new_title
    col["column_name"] = new_title
    api("PATCH", f"/api/v2/meta/columns/{column_id}", json=col)


def delete_column(column_id):
    api("DELETE", f"/api/v2/meta/columns/{column_id}")


def upgrade_relation(owner_id, field_title, workspace_id, dry_run):
    cols = table_columns(owner_id)
    col = cols.get(field_title.lower())
    ltar_title = f"LTAR_{field_title}"
    ltar_col = cols.get(ltar_title.lower())

    if col and col["uidt"] == "LinkToAnotherRecord":
        print(f"=  {field_title}: już v3, pomijam")
        return

    if col and col["uidt"] == "Links":
        print(f"+  {field_title}: upgrade (convertLinkToV2)")
        if dry_run:
            return
        convert_link_to_v2(workspace_id, col["id"])
        cols = table_columns(owner_id)
        col = cols.get(field_title.lower())
        ltar_col = cols.get(ltar_title.lower())

    if not ltar_col:
        print(f"!  {field_title}: brak {ltar_title} po konwersji - sprawdź ręcznie w UI")
        return

    print(f"+  {field_title}: usuwam stare pole (Rollup), zmieniam nazwę {ltar_title} -> {field_title}")
    if dry_run:
        return
    if col:
        delete_column(col["id"])
    rename_column(ltar_col["id"], field_title)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="pokaż plan, nie wywołuj API")
    args = ap.parse_args()

    print(f"NocoDB: {URL}, base: {BASE_ID}{' [DRY RUN]' if args.dry_run else ''}\n")
    ids = existing_tables()
    workspace_id = None if args.dry_run else resolve_workspace_id()

    for owner, field_title, _rel_type, _target in RELATIONS:
        owner_id = ids.get(owner)
        if not owner_id:
            print(f"!  pomijam {owner}.{field_title}: brak tabeli {owner}")
            continue
        upgrade_relation(owner_id, field_title, workspace_id, args.dry_run)

    print("\nSprawdź w UI: pola relacji powinny pokazywać powiązane rekordy")
    print("(LinkToAnotherRecord), nie tylko licznik (Rollup).")
