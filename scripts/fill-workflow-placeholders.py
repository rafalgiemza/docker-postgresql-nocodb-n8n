#!/usr/bin/env python3
r"""Podmienia placeholdery `__...__` w JSON-ach workflow n8n na prawdziwe ID
z żywej instancji NocoDB (workspace, base, tabele, pola, widoki).

Źródła (pliki z placeholderami) nigdy nie są nadpisywane - wynik trafia do
katalogu --out (domyślnie n8n/generated/), gotowy do importu w n8n.

Placeholdery (generowane z żywego schematu, <TABLE>/<FIELD> = tytuł wielkimi
literami, znaki inne niż A-Z0-9 -> `_`):
  __WORKSPACE_ID__              workspace z metadanych bazy (lub NC_WORKSPACE_ID)
  __PROJECT_ID__                NC_CRM_BASE_ID
  __TBL_<TABLE>__               id tabeli,               np. __TBL_LEADS__
  __COL_<TABLE>__<FIELD>__      id pola/relacji (np. field_id w /links/),
                                np. __COL_OFFERS__RECOMMENDATIONS__
  __VIEW_<TABLE>_ID__           id domyślnego widoku tabeli, np. __VIEW_TASKS_ID__
  __NOCODB_BASE_URL__           NC_PUBLIC_URL (domyślnie https://$NC_HOST)
  __N8N_INTERNAL_URL__          N8N_INTERNAL_URL (domyślnie http://n8n:5678)
  __NOCODB_CRED_ID__            N8N_NOCODB_CRED_ID    (id credentiala w n8n)
  __OPENROUTER_CRED_ID__        N8N_OPENROUTER_CRED_ID
  __W<NN>_WORKFLOW_ID__         id workflow w n8n, jeśli jest N8N_API_KEY
                                (dopasowanie po prefiksie nazwy `W<NN>`)

Wymaga: NC_API_TOKEN, NC_CRM_BASE_ID (opcjonalnie NC_LOCAL_URL,
domyślnie http://localhost:8081). Reszta jest opcjonalna - nierozwiązane
placeholdery są raportowane (exit 1 z --strict).

Usage:
  set -a; source .env; set +a
  python3 scripts/fill-workflow-placeholders.py docs/archive/fable/W14_convert_lead.json
  python3 scripts/fill-workflow-placeholders.py docs/archive/fable --out n8n/generated
  python3 scripts/fill-workflow-placeholders.py --list     # wypisz wszystkie znane placeholdery
"""
import argparse
import os
import re
import sys
from pathlib import Path

import requests

NC_URL = os.environ.get("NC_LOCAL_URL", "http://localhost:8081").rstrip("/")
TOKEN = os.environ.get("NC_API_TOKEN")
BASE_ID = os.environ.get("NC_CRM_BASE_ID")
N8N_URL = os.environ.get("N8N_LOCAL_URL", "http://localhost:5678").rstrip("/")

# Luźny wzorzec tylko do raportowania nierozwiązanych (dopuszcza `__` w środku,
# np. __COL_OFFERS__RECOMMENDATIONS__); podmiana idzie po znanych kluczach.
PLACEHOLDER_RE = re.compile(r"__[A-Z0-9]+(?:_{1,2}[A-Z0-9]+)*__")


def slug(s):
    return re.sub(r"[^A-Z0-9]+", "_", s.upper()).strip("_")


def get(base, path, headers, **params):
    try:
        r = requests.get(f"{base}{path}", headers=headers, params=params, timeout=30)
    except requests.RequestException as e:
        sys.exit(f"Brak połączenia z {base} ({type(e).__name__}).")
    if not r.ok:
        sys.exit(f"{r.status_code} na GET {base}{path}: {r.text[:300]}")
    return r.json()


def nocodb_map():
    h = {"xc-token": TOKEN}
    base = get(NC_URL, f"/api/v2/meta/bases/{BASE_ID}", h)
    ws = os.environ.get("NC_WORKSPACE_ID") or base.get("fk_workspace_id") or ""
    m = {"__PROJECT_ID__": BASE_ID}
    if ws:
        m["__WORKSPACE_ID__"] = ws
    tables = get(NC_URL, f"/api/v2/meta/bases/{BASE_ID}/tables", h, limit=200)["list"]
    for t in tables:
        ts = slug(t["title"])
        m[f"__TBL_{ts}__"] = t["id"]
        detail = get(NC_URL, f"/api/v2/meta/tables/{t['id']}", h)
        for c in detail.get("columns", []):
            m[f"__COL_{ts}__{slug(c['title'])}__"] = c["id"]
        views = get(NC_URL, f"/api/v2/meta/tables/{t['id']}/views", h).get("list", [])
        default = next((v for v in views if v.get("is_default")), views[0] if views else None)
        if default:
            m[f"__VIEW_{ts}_ID__"] = default["id"]
    return m


def env_map():
    m = {}
    public = os.environ.get("NC_PUBLIC_URL") or (
        f"https://{os.environ['NC_HOST']}" if os.environ.get("NC_HOST") else "")
    pairs = {
        "__NOCODB_BASE_URL__": public,
        "__N8N_INTERNAL_URL__": os.environ.get("N8N_INTERNAL_URL", "http://n8n:5678"),
        "__NOCODB_CRED_ID__": os.environ.get("N8N_NOCODB_CRED_ID", ""),
        "__OPENROUTER_CRED_ID__": os.environ.get("N8N_OPENROUTER_CRED_ID", ""),
    }
    m.update({k: v for k, v in pairs.items() if v})
    return m


def n8n_workflow_map():
    key = os.environ.get("N8N_API_KEY")
    if not key or key.startswith("API_KEY_PLACEHOLDER"):
        return {}
    data = get(N8N_URL, "/api/v1/workflows", {"X-N8N-API-KEY": key}, limit=250)["data"]
    m = {}
    for w in data:
        mt = re.match(r"\s*(W\d+[a-z]?)\b", w["name"], re.I)
        if mt:
            m[f"__{mt.group(1).upper()}_WORKFLOW_ID__"] = w["id"]
    return m


def collect(paths):
    files = []
    for p in map(Path, paths):
        files += sorted(p.glob("*.json")) if p.is_dir() else [p]
    return [f for f in files if f.name != "schema_map.json" and f.name != "meta.json"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("inputs", nargs="*", help="pliki JSON lub katalogi")
    ap.add_argument("--out", default="n8n/generated", help="katalog wyjściowy")
    ap.add_argument("--list", action="store_true", help="wypisz znane placeholdery i wyjdź")
    ap.add_argument("--strict", action="store_true", help="exit 1 gdy zostały nierozwiązane")
    a = ap.parse_args()

    if not TOKEN or not BASE_ID:
        sys.exit("Brak NC_API_TOKEN / NC_CRM_BASE_ID w środowisku - patrz .env.example.")
    mapping = {**nocodb_map(), **env_map(), **n8n_workflow_map()}

    if a.list:
        for k, v in sorted(mapping.items()):
            print(f"{k} = {v}")
        return
    if not a.inputs:
        ap.error("podaj pliki/katalogi albo --list")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    unresolved = {}
    for f in collect(a.inputs):
        text = f.read_text(encoding="utf-8")
        if mapping:
            known = re.compile("|".join(map(re.escape, sorted(mapping, key=len, reverse=True))))
            text = known.sub(lambda m: mapping[m.group(0)], text)
        left = sorted(set(PLACEHOLDER_RE.findall(text)))
        if left:
            unresolved[f.name] = left
        (out / f.name).write_text(text, encoding="utf-8")
        print(f"{f.name} -> {out / f.name}")
    for name, left in unresolved.items():
        print(f"UWAGA {name}: nierozwiązane {', '.join(left)}", file=sys.stderr)
    if unresolved and a.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
