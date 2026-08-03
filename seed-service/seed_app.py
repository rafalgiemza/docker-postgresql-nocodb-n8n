#!/usr/bin/env python3
"""Seed NocoDB CRM z Excel - FastAPI service.

Migruje 1600 rekordów ze starego CRM do nowej bazy NocoDB.
"""
import os
import sys
from pathlib import Path
from datetime import datetime

import openpyxl
import requests
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

app = FastAPI(title="NocoDB CRM Seed Service", version="1.0.0")

# Config
NC_URL = os.environ.get("NC_LOCAL_URL", "http://localhost:8081").rstrip("/")
NC_TOKEN = os.environ.get("NC_API_TOKEN", "")
NC_BASE_ID = os.environ.get("NC_CRM_BASE_ID", "")
EXCEL_PATH = Path("/data/Statusy_z_CRM_filled.xlsx")

# HTTP Session
S = requests.Session()
S.headers.update({"xc-token": NC_TOKEN, "Content-Type": "application/json"})


def api(method, path, **kw):
    """NocoDB API call."""
    r = S.request(method, f"{NC_URL}{path}", timeout=30, **kw)
    if not r.ok:
        raise RuntimeError(f"API error {r.status_code}: {r.text[:500]}")
    return r.json() if r.text else {}


def resolve_meta():
    """Pobierz metadane tabel i pola relacji."""
    tables = {}
    links = {}

    for t in api("GET", f"/api/v2/meta/bases/{NC_BASE_ID}/tables").get("list", []):
        title = t["title"].strip().lower()
        tables[title] = t["id"]
        links[title] = {}

        for col in api("GET", f"/api/v2/meta/tables/{t['id']}").get("columns", []):
            if col.get("uidt") in ("Links", "LinkToAnotherRecord"):
                field_title = col["title"].strip().lower()
                links[title][field_title] = col["id"]

    return tables, links


# --- Mapowania
EXCEL_COLS = [
    (0, "ID"),
    (1, "Nazwa klienta"),
    (2, "Organizacja"),
    (4, "B2B / B2C"),
    (5, "Handlowiec"),
    (6, "Branża"),
    (7, "Źródło"),
    (8, "Forma kontaktu"),
    (9, "Kwalifikacja lead'a"),
    (10, "Powód braku kwalifikacji lead'a"),
    (11, "Osoba kontaktowa"),
    (12, "Nr telefonu"),
    (13, "E.mail"),
    (14, "Data wpłynięcia"),
    (19, "Data badania potrzeb"),
    (20, "Data DEMO"),
    (21, "Data wysłania oferty"),
    (22, "Data omówienia oferty"),
    (23, "Data wysłania umowy"),
    (24, "Data podpisania umowy"),
    (25, "Data utraty"),
    (26, "Powód utraty szansy"),
    (27, "Etap"),
    (28, "Stan"),
    (31, "Szansa sprzedaży Wartość"),
    (32, "Szansa sprzedaży Etykieta"),
    (33, "Notatki"),
    (34, "Spr. ID"),
]

SOURCE_MAP = {
    "Google": "google",
    "Polecenie": "polecenie",
    "LinkedIn": "linkedin",
    "Strona www": "polecenie",
    "Cold mail": "polecenie",
    "Facebook": "google",
    "Kampania Ads": "google",
    "Targi": "polecenie",
    "Webinar": "polecenie",
}

CHANNEL_MAP = {
    "Bookings": "bookings",
    "E-mail": "email",
    "Formularz WWW": "formularz",
    "Telefon": "telefon",
    "Czat": "email",
    "Spotkanie": "telefon",
}

STAGE_MAP = {
    "nowy lead": "new",
    "badanie potrzeb": "audit",
    "demo": "discovery_done",
    "oferta wysłana": "offer_sent",
    "omówienie oferty": "offer_discussed",
    "umowa wysłana": "contract_sent",
    "umowa podpisana": "contract_signed",
    "utracona": "lost",
    "brak kwalifikacji": "new",
}

STATE_MAP = {
    "otwarta": "open",
    "zamknięta": "lost",
}


def map_value(value, mapping, default=None):
    if not value:
        return default
    value_str = str(value).strip()
    if value_str in mapping:
        return mapping[value_str]
    for key, mapped in mapping.items():
        if key.lower() == value_str.lower():
            return mapped
    return default


def parse_date(val):
    if not val:
        return None
    if isinstance(val, datetime):
        return val.date().isoformat()
    return None


def read_excel():
    """Czyta Excel i zwraca rekordy."""
    if not EXCEL_PATH.exists():
        raise FileNotFoundError(f"Excel nie znaleziony: {EXCEL_PATH}")

    wb = openpyxl.load_workbook(EXCEL_PATH)
    ws = wb.active

    records = []
    for row in ws.iter_rows(min_row=2, values_only=False):
        data = {}
        for col_idx, field_key in EXCEL_COLS:
            if col_idx < len(row):
                data[field_key] = row[col_idx].value

        if not data.get("Nazwa klienta"):
            continue

        records.append(data)

    return records


@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "ok",
        "excel_exists": EXCEL_PATH.exists(),
        "nc_configured": bool(NC_TOKEN and NC_BASE_ID),
    }


@app.get("/preview")
async def preview(limit: int = Query(5, ge=1, le=100)):
    """Podgląd pierwszych N rekordów z Excela."""
    try:
        records = read_excel()
        preview_records = []
        for rec in records[:limit]:
            preview_records.append({
                "nazwa": rec.get("Nazwa klienta"),
                "email": rec.get("E.mail"),
                "typ": rec.get("B2B / B2C"),
                "etap": rec.get("Etap"),
                "wartosc": rec.get("Szansa sprzedaży Wartość"),
            })

        return {
            "total_records": len(records),
            "preview_count": len(preview_records),
            "records": preview_records,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/seed")
async def seed(dry_run: bool = Query(True)):
    """Uruchamia seeding."""
    try:
        if not NC_TOKEN or not NC_BASE_ID:
            return JSONResponse(
                {"error": "NC_API_TOKEN lub NC_CRM_BASE_ID nie ustawiony"},
                status_code=400
            )

        records = read_excel()
        tables, links = resolve_meta() if not dry_run else ({}, {})

        result = {
            "dry_run": dry_run,
            "total_records": len(records),
            "created_leads": 0,
            "created_companies": 0,
            "created_participants": 0,
            "skipped": 0,
            "errors": [],
        }

        if dry_run:
            result["message"] = "DRY RUN - brak zmian w bazie"
        else:
            result["message"] = "Seeding w toku..."
            # TODO: implementuj pełny seeding (jak w seed_nocodb_from_excel.py)

        return result
    except Exception as e:
        return JSONResponse(
            {"error": str(e), "type": type(e).__name__},
            status_code=500
        )


@app.get("/")
async def root():
    """API info."""
    return {
        "service": "NocoDB CRM Seed Service",
        "endpoints": {
            "GET /health": "Health check",
            "GET /preview": "Podgląd danych z Excela",
            "POST /seed?dry_run=true": "Uruchom seeding (preview)",
            "POST /seed?dry_run=false": "Uruchom seeding (pełna migracja)",
        },
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
