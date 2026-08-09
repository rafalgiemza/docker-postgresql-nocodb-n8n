#!/usr/bin/env python3
r"""Zrzuca żywy schemat CRM (id tabel, id pól, cele relacji, nazwy tabel
łączących _nc_m2m_*) z NocoDB przez Meta API v2 do pliku JSON.

PO CO: rekonstrukcja workflowów n8n (patrz `docs/archive/fable/W9_generate_offer.json`)
po migracji na `nocodb_crm_schema_v3.md` + `docs/archive/fable/feedback-tables-1.md`
wymaga prawdziwych id tabel/pól z instancji, na której faktycznie stoi nowy
schemat (16 tabel) — nie da się ich wyczytać z gita, bo `init-schema.py`
nadaje je dynamicznie przy tworzeniu. Ten skrypt zamiast zgadywać/czytać
`.env`, zrzuca je do pliku, który można bezpiecznie przejrzeć (bez sekretów
w środku — same tytuły/id tabel i pól).

`junction_table_name` dla pól relacji `mm` (i `hm` PO `make upgrade-links` —
patrz nagłówek `scripts/upgrade-links.py`, convertLinkToV2 tworzy fizyczną
tabelę łączącą też dla `hm`) to najlepsza dostępna z Meta API przybliżenie
klucza `_nc_m2m_*`, pod którym NocoDB osadza powiązane rekordy w payloadzie
webhooka. NIEZWERYFIKOWANE NA ŻYWO w tej sesji (brak dostępnej instancji) —
jeśli po uruchomieniu klucz w realnym webhooku wygląda inaczej, źródłem
prawdy jest jeden realny payload (w n8n: otwórz trigger node -> "Listen for
test event" -> kliknij przycisk raz na testowym rekordzie).

Wymaga w środowisku (patrz .env.example): NC_API_TOKEN, NC_CRM_BASE_ID.
Opcjonalnie NC_LOCAL_URL (domyślnie http://localhost:8081).

Usage:
  make dump-crm-schema
  # albo bezpośrednio:
  set -a; source .env; set +a
  python3 scripts/dump-crm-schema.py [--out docs/archive/fable/schema_map.json]
"""
import argparse
import json
import os
import sys

import requests

URL = os.environ.get("NC_LOCAL_URL", "http://localhost:8081").rstrip("/")
TOKEN = os.environ.get("NC_API_TOKEN")
BASE_ID = os.environ.get("NC_CRM_BASE_ID")

if not TOKEN or not BASE_ID:
    sys.exit("Brak NC_API_TOKEN / NC_CRM_BASE_ID w środowisku - patrz .env.example.")

S = requests.Session()
S.headers.update({"xc-token": TOKEN})

_RELATION_UIDT = ("Links", "LinkToAnotherRecord", "Rollup")


def api(method, path, **kw):
    try:
        r = S.request(method, f"{URL}{path}", timeout=30, **kw)
    except requests.RequestException as e:
        sys.exit(f"Nie moge sie polaczyc z NocoDB ({URL}): {type(e).__name__}. "
                 f"Sprawdz NC_LOCAL_URL / czy instancja jest dostepna.")
    if not r.ok:
        sys.exit(f"NocoDB API error {r.status_code} on {method} {path}: {r.text[:500]}")
    return r.json() if r.text else {}


def dump():
    tables = api("GET", f"/api/v2/meta/bases/{BASE_ID}/tables").get("list", [])
    titles_by_id = {t["id"]: t["title"] for t in tables}

    out = {}
    for t in tables:
        full = api("GET", f"/api/v2/meta/tables/{t['id']}")
        fields = {}
        for c in full.get("columns", []):
            entry = {"id": c["id"], "uidt": c["uidt"]}
            co = c.get("colOptions") or {}
            if c["uidt"] in _RELATION_UIDT and co:
                if co.get("type"):
                    entry["relation_type"] = co["type"]  # hm / mm / bt / oo
                related_id = co.get("fk_related_model_id")
                if related_id:
                    entry["related_table"] = titles_by_id.get(related_id, related_id)
                mm_id = co.get("fk_mm_model_id")
                if mm_id:
                    try:
                        mm_model = api("GET", f"/api/v2/meta/tables/{mm_id}")
                        entry["junction_table_name"] = mm_model.get("table_name")
                    except SystemExit:
                        pass
                # surowy blob jako siatka bezpieczenstwa - gdyby powyzsze
                # klucze nie odpowiadaly rzeczywistej odpowiedzi API
                entry["_raw_colOptions"] = co
            fields[c["title"]] = entry
        out[t["title"]] = {
            "id": t["id"],
            "source_id": t.get("source_id"),
            "fields": fields,
        }
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/archive/fable/schema_map.json",
                    help="gdzie zapisac wynik (domyslnie docs/archive/fable/schema_map.json)")
    args = ap.parse_args()

    print(f"NocoDB: {URL}, base: {BASE_ID}")
    data = dump()
    n_fields = sum(len(v["fields"]) for v in data.values())
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
    print(f"Zapisano {len(data)} tabel, {n_fields} pol -> {args.out}")
