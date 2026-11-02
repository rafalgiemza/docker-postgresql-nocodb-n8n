"""HTTP wrapper nad legacy_import.py - wolany przez n8n (W22 import).

Bezstanowy: n8n przysyla plik CSV, serwis zapisuje do Postgresa (schemat crm)
i zwraca JSON z licznikami/ostrzezeniami. ZERO integracji z NocoDB (decyzja:
.ai/rules/nocodb.md, sekcja 6 - NocoDB nie ustawi created_at).
Brak portow na zewnatrz; woła go tylko n8n z sieci wewnetrznej.
"""
import hashlib
import json
import os
from datetime import date

from fastapi import FastAPI, File, Form, Header, HTTPException, Response, UploadFile

import legacy_export as le
import legacy_import as li

SCHEMA_MAP_PATH = os.environ.get("SCHEMA_MAP_PATH", "/data/schema_map.json")
TOKEN = os.environ.get("CRM_LEGACY_TOKEN", "")

app = FastAPI(title="crm-legacy-service")


class PsycopgDb:
    """Interfejs bazy z legacy_import.py oparty o psycopg (autocommit - BEGIN/
    COMMIT/ROLLBACK sa w samym skrypcie SQL)."""

    def __init__(self):
        import psycopg
        self.conn = psycopg.connect(
            host=os.environ.get("PGHOST", "postgres"),
            port=int(os.environ.get("PGPORT", "5432")),
            dbname=os.environ["APP_DB"],
            user=os.environ["CRM_LEGACY_USER"],
            password=os.environ["CRM_LEGACY_PASSWORD"],
            connect_timeout=10,  # lepiej blad w raporcie niz zawieszony przycisk
            autocommit=True)
        self.notices = []
        self.conn.add_notice_handler(lambda d: self.notices.append(d.message_primary))

    def run(self, sql, tuples=False):
        with self.conn.cursor() as cur:
            cur.execute(sql)
            if tuples:
                return [[("" if v is None else str(v)) for v in row]
                        for row in cur.fetchall()]
        out, self.notices = "\n".join(f"NOTICE:  {n}" for n in self.notices), []
        return out

    def close(self):
        self.conn.close()


def get_db():
    return PsycopgDb()


def check_token(x_token):
    if TOKEN and x_token != TOKEN:
        raise HTTPException(401, "Zly token")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/import")
async def import_csv(file: UploadFile = File(...), dry_run: bool = Form(True),
                     export_date: str = Form("2026-10-30"),
                     expect_sha256: str = Form(""),
                     x_token: str = Header(default="")):
    """dry_run=true (domyslnie): pelny import w transakcji + ROLLBACK.
    dry_run=false wymaga expect_sha256 = skrot tego samego pliku zwrocony
    wczesniej przez dry-run (nie zapiszemy pliku, ktorego nie sprawdzono)."""
    check_token(x_token)
    data = await file.read()
    if not dry_run and expect_sha256 != hashlib.sha256(data).hexdigest():
        raise HTTPException(
            409, "Plik nie byl sprawdzony - najpierw kliknij \"Sprawdz import\" "
                 "dla tego pliku (skrot sie nie zgadza).")
    with open(SCHEMA_MAP_PATH, encoding="utf-8") as f:
        schema_map = json.load(f)
    db = get_db()
    try:
        return li.run_import(db, data, schema_map, apply=not dry_run,
                             export_date=date.fromisoformat(export_date))
    except li.LegacyError as e:
        # 422: n8n pokazuje komunikat userowi w polu raportu
        raise HTTPException(422, str(e))
    finally:
        db.close()


@app.post("/export")
def export_csv(x_token: str = Header(default="")):
    """Caly CRM z Postgresa -> CSV w formacie starego CRM (32 kolumny, daty
    MM/DD/YYYY, UTF-8). Tylko odczyt."""
    check_token(x_token)
    with open(SCHEMA_MAP_PATH, encoding="utf-8") as f:
        schema_map = json.load(f)
    db = get_db()
    try:
        data, n = le.run_export(db, schema_map)
    except li.LegacyError as e:
        raise HTTPException(422, str(e))
    finally:
        db.close()
    name = f"crm-export-{date.today().isoformat()}.csv"
    return Response(content=data, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"',
                             "X-Rows": str(n)})
