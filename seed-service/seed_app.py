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


def create_or_find_company(table_id, name, industry=None):
    """Szuka lub tworzy firmę (B2B)."""
    if not name or not name.strip():
        return None

    name = name.strip()
    # Szukaj istniejącej
    res = api("GET", f"/api/v2/tables/{table_id}/records",
              params={"where": f"(name,like,%{name}%)"})
    existing = res.get("list", [])
    if existing:
        return existing[0].get("Id")

    # Utwórz nową
    record = {"name": name}
    if industry:
        industry_map = {
            "IT": "IT", "Logistyka": "logistyka", "Edukacja": "edukacja",
            "Usługi finansowe": "finanse", "Medyczna": "medyczna",
            "Produkcja": "produkcja", "Handel": "handel",
        }
        record["industry"] = map_value(industry, industry_map) or "inne"

    res = api("POST", f"/api/v2/tables/{table_id}/records", json=record)
    return res.get("Id") or (res[0].get("Id") if isinstance(res, list) else None)


def create_lead(table_id, excel_data):
    """Tworzy lead z danych Excela."""
    lead_data = {
        "contact_name": (excel_data.get("Nazwa klienta") or "").strip(),
        "contact_email": (excel_data.get("E.mail") or "").strip() or None,
        "contact_phone": (excel_data.get("Nr telefonu") or "").strip() or None,
        "type": excel_data.get("B2B / B2C", "B2C"),
        "source": map_value(excel_data.get("Źródło"), SOURCE_MAP),
        "contact_channel": map_value(excel_data.get("Forma kontaktu"), CHANNEL_MAP),
        "qualification": map_value(excel_data.get("Kwalifikacja lead'a"),
                                   {"MQL": "MQL", "SQL": "SQL"}),
        "stage": map_value(excel_data.get("Etap"), STAGE_MAP) or "new",
        "state": map_value(excel_data.get("Stan"), STATE_MAP) or "open",
        "value": excel_data.get("Szansa sprzedaży Wartość") or None,
        "notes": (excel_data.get("Notatki") or "").strip() or None,
        "legacy_id": str(excel_data.get("Spr. ID") or "").strip() or None,
        "industry": map_value(excel_data.get("Branża"), {
            "IT": "IT", "Logistyka": "logistyka", "Edukacja": "edukacja",
            "Usługi finansowe": "finanse", "Medyczna": "medyczna",
            "Produkcja": "produkcja", "Handel": "handel",
        }) or "inne",
    }
    lead_data = {k: v for k, v in lead_data.items() if v is not None and v != ""}

    res = api("POST", f"/api/v2/tables/{table_id}/records", json=lead_data)
    return res.get("Id") or (res[0].get("Id") if isinstance(res, list) else None)


def link_records(table_id, field_id, record_id, target_ids):
    """Linkuje rekordy."""
    if not target_ids or not record_id:
        return
    if not isinstance(target_ids, list):
        target_ids = [target_ids]

    api("POST", f"/api/v2/tables/{table_id}/links/{field_id}/records/{record_id}",
        json=[{"Id": i} for i in target_ids if i])


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
    """Uruchamia seeding - czyta Excel i zasilaj NocoDB."""
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
            return result

        # --- PEŁNY SEEDING ---
        for idx, rec in enumerate(records, 1):
            try:
                contact_name = (rec.get("Nazwa klienta") or "").strip()
                legacy_id = str(rec.get("Spr. ID") or "").strip()

                # Sprawdź dedup
                if legacy_id:
                    existing = api("GET", f"/api/v2/tables/{tables.get('leads')}/records",
                                 params={"where": f"(legacy_id,eq,{legacy_id})"})
                    if existing.get("list"):
                        result["skipped"] += 1
                        continue

                # Utwórz lead
                lead_id = create_lead(tables["leads"], rec)
                if not lead_id:
                    result["errors"].append(f"Lead {contact_name}: nie utworzono")
                    result["skipped"] += 1
                    continue
                result["created_leads"] += 1

                # Dla B2B: utwórz/link firmę
                if rec.get("B2B / B2C") == "B2B":
                    org_name = rec.get("Organizacja")
                    if org_name and org_name.strip():
                        company_id = create_or_find_company(
                            tables["companies"], org_name, rec.get("Branża"))
                        if company_id:
                            result["created_companies"] += 1
                            # Linkuj lead -> company
                            company_field_id = links.get("leads", {}).get("company")
                            if company_field_id:
                                link_records(tables["leads"], company_field_id,
                                           lead_id, company_id)

                # Utwórz participant
                participant_data = {
                    "full_name": contact_name,
                    "email": (rec.get("E.mail") or "").strip() or None,
                }
                participant_data = {k: v for k, v in participant_data.items() if v}

                p_res = api("POST", f"/api/v2/tables/{tables['participants']}/records",
                           json=participant_data)
                participant_id = p_res.get("Id") or (p_res[0].get("Id")
                                                      if isinstance(p_res, list) else None)
                if participant_id:
                    result["created_participants"] += 1
                    # Linkuj lead -> participant
                    participant_field_id = links.get("leads", {}).get("participants")
                    if participant_field_id:
                        link_records(tables["leads"], participant_field_id,
                                   lead_id, participant_id)

                if idx % 100 == 0:
                    print(f"  {idx}/{len(records)} ...")

            except Exception as e:
                result["errors"].append(f"{idx}. {str(e)[:100]}")
                result["skipped"] += 1
                continue

        result["message"] = f"Seeding ukończony: {result['created_leads']} leads, " \
                           f"{result['created_companies']} companies, " \
                           f"{result['created_participants']} participants"
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
