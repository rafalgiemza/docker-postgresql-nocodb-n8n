#!/usr/bin/env python3
"""Seed NocoDB CRM z Excel - FastAPI service.

Migruje rekordy ze starego CRM (Excel) do NocoDB.
Obsługuje: fixed file lub upload, fixed base_id lub query param.

Zaktualizowane pod schemat po fable/feedback-tables-1.md (2026-08-06) -
patrz fable/create_offer_tables.py. Wymaga bazy stworzonej TĄ wersją skryptu
(pola `lead_name`/`lead_type`/`lead_source`/`deal_value` na `leads`, nowe
listy opcji `lead_source`/`contact_channel`/`industry`; tabela `participants`
zostaje bez zmian).
"""
import os
import tempfile
from pathlib import Path
from datetime import datetime

import openpyxl
import requests
from fastapi import FastAPI, Query, UploadFile, File
from fastapi.responses import JSONResponse

app = FastAPI(title="NocoDB CRM Seed Service", version="1.0.0")

# Config (ENV fallback)
DEFAULT_NC_URL = os.environ.get("NC_LOCAL_URL", "http://localhost:8081").rstrip("/")
DEFAULT_NC_TOKEN = os.environ.get("NC_API_TOKEN", "")
DEFAULT_NC_BASE_ID = os.environ.get("NC_CRM_BASE_ID", "")
DEFAULT_EXCEL_PATH = Path("/data/Statusy_z_CRM_filled.xlsx")


def api(method, path, token, url, **kw):
    """NocoDB API call - z parametrami token/url."""
    s = requests.Session()
    s.headers.update({"xc-token": token, "Content-Type": "application/json"})
    r = s.request(method, f"{url}{path}", timeout=30, **kw)
    if not r.ok:
        raise RuntimeError(f"API error {r.status_code}: {r.text[:500]}")
    return r.json() if r.text else {}


def resolve_meta(token, url, base_id):
    """Pobierz metadane tabel i pola relacji."""
    tables = {}
    links = {}

    for t in api("GET", f"/api/v2/meta/bases/{base_id}/tables", token, url).get("list", []):
        title = t["title"].strip().lower()
        tables[title] = t["id"]
        links[title] = {}

        for col in api("GET", f"/api/v2/meta/tables/{t['id']}", token, url).get("columns", []):
            if col.get("uidt") in ("Links", "LinkToAnotherRecord"):
                field_title = col["title"].strip().lower()
                links[title][field_title] = col["id"]

    return tables, links


# --- Mapowania Excela na kolumny (0-based index)
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

# Mapowania wartości -> nowe listy opcji z fable/create_offer_tables.py
# (feedback-tables-1.md, 2026-08-06). Świadomie BEZ fallbacków na "najbliższą"
# opcję tam, gdzie nowa lista po prostu nie ma odpowiednika - lepiej zostawić
# pole puste i zapisać oryginał w notes niż udawać np. że to "Google".
SOURCE_MAP = {
    "Google": "Google",
    "Polecenie": "Recommendation",
    "LinkedIn": "LinkedIn",
    "Facebook": "Facebook",
    "Webinar": "Webinar",
    "Cold mail": "Outreach",
    # BEZ mapowania (-> notes): "Strona www", "Kampania Ads", "Targi"
}

CHANNEL_MAP = {
    "Bookings": "Bookings",
    "E-mail": "Mail",
    "Formularz WWW": "Formularz",
    "Telefon": "Telefon",
    # BEZ mapowania (-> notes): "Czat", "Spotkanie"
}

INDUSTRY_MAP = {
    "IT": "IT",
    "Logistyka": "Transport/Logistics",
    "Edukacja": "Education",
    "Finanse": "Finance",
    "Usługi finansowe": "Finance",
    "Medyczna": "Medicine",
    "Produkcja": "Manufacturing",
    "Handel": "Retail",
}

QUALIFICATION_MAP = {
    "MQL": "MQL",
    "SQL": "SQL",
    "Niekwalifikowany": "unqualified",
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

LOSS_REASON_MAP = {
    "Cena": "cena",
    "Brak decyzji": "brak_decyzji",
    "Konkurencja": "konkurencja",
    "Przesunięte w czasie": "przesuniete_w_czasie",
}

LEAD_TYPE_MAP = {
    "B2B": "B2B",
    "B2C": "B2C",
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
    if isinstance(val, str):
        try:
            return datetime.strptime(val, "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None
    return None


def read_excel():
    """Czyta Excel i zwraca rekordy."""
    if not DEFAULT_EXCEL_PATH.exists():
        raise FileNotFoundError(f"Excel nie znaleziony: {DEFAULT_EXCEL_PATH}")

    wb = openpyxl.load_workbook(DEFAULT_EXCEL_PATH)
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


def build_lead_data(excel_data):
    """Mapuje rekord Excela na pola `leads`. Wartości bez odpowiednika w
    nowych listach opcji trafiają do `notes`, żeby nic nie zgubić."""
    unmapped = []

    def mapped(value, mapping, label):
        result = map_value(value, mapping)
        if value and not result:
            unmapped.append(f"{label} (stary CRM): {str(value).strip()}")
        return result

    lead_data = {
        "lead_name": (excel_data.get("Nazwa klienta") or "").strip(),
        "contact_email": (excel_data.get("E.mail") or "").strip() or None,
        "contact_phone": (excel_data.get("Nr telefonu") or "").strip() or None,
        "lead_type": mapped(excel_data.get("B2B / B2C"), LEAD_TYPE_MAP, "B2B/B2C") or "B2C",
        "lead_source": mapped(excel_data.get("Źródło"), SOURCE_MAP, "Źródło"),
        "contact_channel": mapped(excel_data.get("Forma kontaktu"), CHANNEL_MAP, "Forma kontaktu"),
        "qualification": mapped(excel_data.get("Kwalifikacja lead'a"), QUALIFICATION_MAP, "Kwalifikacja"),
        "disqualify_reason": map_value(
            excel_data.get("Powód braku kwalifikacji lead'a"), LOSS_REASON_MAP),
        "stage": map_value(excel_data.get("Etap"), STAGE_MAP) or "new",
        "state": map_value(excel_data.get("Stan"), STATE_MAP) or "open",
        "loss_reason": map_value(excel_data.get("Powód utraty szansy"), LOSS_REASON_MAP),
        "deal_value": excel_data.get("Szansa sprzedaży Wartość") or None,
        "label": map_value(excel_data.get("Szansa sprzedaży Etykieta"),
                          {"Gorąca": "hot", "Oferta specjalna": "oferta_specjalna"}),
        "legacy_id": str(excel_data.get("Spr. ID") or "").strip() or None,
        "industry": mapped(excel_data.get("Branża"), INDUSTRY_MAP, "Branża"),
        "offer_sent_at": parse_date(excel_data.get("Data wysłania oferty")),
        "contract_sent_at": parse_date(excel_data.get("Data wysłania umowy")),
        "closed_at": parse_date(excel_data.get("Data podpisania umowy")),
    }

    notes_parts = [(excel_data.get("Notatki") or "").strip()] + unmapped
    lead_data["notes"] = "\n".join(p for p in notes_parts if p) or None

    return {k: v for k, v in lead_data.items() if v is not None and v != ""}


def create_or_find_company(table_id, token, url, name, industry=None):
    """Szuka lub tworzy firmę (B2B)."""
    if not name or not name.strip():
        return None

    name = name.strip()
    res = api("GET", f"/api/v2/tables/{table_id}/records", token, url,
              params={"where": f"(name,like,%{name}%)"})
    existing = res.get("list", [])
    if existing:
        return existing[0].get("Id")

    record = {"name": name}
    if industry:
        mapped_industry = map_value(industry, INDUSTRY_MAP)
        if mapped_industry:
            record["industry"] = mapped_industry
        else:
            record["notes"] = f"Branża (stary CRM): {str(industry).strip()}"

    res = api("POST", f"/api/v2/tables/{table_id}/records", token, url, json=record)
    return res.get("Id") or (res[0].get("Id") if isinstance(res, list) else None)


def link_records(table_id, field_id, record_id, target_ids, token, url):
    """Linkuje rekordy."""
    if not target_ids or not record_id:
        return
    if not isinstance(target_ids, list):
        target_ids = [target_ids]

    api("POST", f"/api/v2/tables/{table_id}/links/{field_id}/records/{record_id}",
        token, url, json=[{"Id": i} for i in target_ids if i])


def seed_records(records, token, url, base_id):
    """Seeduje leads/companies/participants do NocoDB. Współdzielone przez
    /seed i /seed-upload, żeby mapowanie pól nie rozjeżdżało się między
    dwiema kopiami tej samej logiki."""
    tables, links = resolve_meta(token, url, base_id)
    if not all(t in tables for t in ["leads", "companies", "participants"]):
        raise RuntimeError("Brakuje tabel: leads, companies, participants")

    result = {
        "total_records": len(records),
        "created_leads": 0,
        "created_companies": 0,
        "created_participants": 0,
        "skipped": 0,
        "errors": [],
    }

    for idx, rec in enumerate(records, 1):
        contact_name = (rec.get("Nazwa klienta") or "").strip()
        try:
            legacy_id = str(rec.get("Spr. ID") or "").strip()

            if legacy_id:
                existing = api("GET", f"/api/v2/tables/{tables['leads']}/records",
                             token, url, params={"where": f"(legacy_id,eq,{legacy_id})"})
                if existing.get("list"):
                    result["skipped"] += 1
                    continue

            lead_data = build_lead_data(rec)
            res = api("POST", f"/api/v2/tables/{tables['leads']}/records",
                     token, url, json=lead_data)
            lead_id = res.get("Id") or (res[0].get("Id") if isinstance(res, list) else None)
            if not lead_id:
                result["errors"].append(f"Lead {contact_name}: nie utworzono")
                result["skipped"] += 1
                continue
            result["created_leads"] += 1

            # Dla B2B: utwórz/link firmę
            if str(rec.get("B2B / B2C") or "").strip() == "B2B":
                org_name = rec.get("Organizacja")
                if org_name and org_name.strip():
                    company_id = create_or_find_company(
                        tables["companies"], token, url, org_name, rec.get("Branża"))
                    if company_id:
                        result["created_companies"] += 1
                        company_field_id = links.get("leads", {}).get("company")
                        if company_field_id:
                            link_records(tables["leads"], company_field_id, lead_id,
                                       company_id, token, url)

            # Utwórz participant
            participant_data = {
                "full_name": contact_name,
                "email": (rec.get("E.mail") or "").strip() or None,
            }
            participant_data = {k: v for k, v in participant_data.items() if v}

            p_res = api("POST", f"/api/v2/tables/{tables['participants']}/records",
                       token, url, json=participant_data)
            participant_id = p_res.get("Id") or (p_res[0].get("Id")
                                                  if isinstance(p_res, list) else None)
            if participant_id:
                result["created_participants"] += 1
                participant_field_id = links.get("leads", {}).get("participants")
                if participant_field_id:
                    link_records(tables["leads"], participant_field_id, lead_id,
                               participant_id, token, url)

            if idx % 100 == 0:
                print(f"  {idx}/{len(records)} ...")

        except Exception as e:
            result["errors"].append(f"{idx}. {str(e)[:300]}")
            result["skipped"] += 1
            continue

    result["message"] = f"Seeding ukończony: {result['created_leads']} leads, " \
                       f"{result['created_companies']} companies, " \
                       f"{result['created_participants']} participants"
    return result


@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "ok",
        "excel_exists": DEFAULT_EXCEL_PATH.exists(),
        "nc_configured": bool(DEFAULT_NC_TOKEN and DEFAULT_NC_BASE_ID),
    }


@app.get("/preview")
async def preview(limit: int = Query(5, ge=1, le=100)):
    """Podgląd pierwszych N rekordów z Excela."""
    try:
        records = read_excel()
        preview_records = [
            {
                "nazwa": rec.get("Nazwa klienta"),
                "email": rec.get("E.mail"),
                "typ": rec.get("B2B / B2C"),
                "etap": rec.get("Etap"),
                "wartosc": rec.get("Szansa sprzedaży Wartość"),
            }
            for rec in records[:limit]
        ]

        return {
            "total_records": len(records),
            "preview_count": len(preview_records),
            "records": preview_records,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/seed")
async def seed(dry_run: bool = Query(True)):
    """Uruchamia seeding - czyta Excel i zasilaj NocoDB (fixed file)."""
    try:
        if not DEFAULT_NC_TOKEN or not DEFAULT_NC_BASE_ID:
            return JSONResponse(
                {"error": "NC_API_TOKEN lub NC_CRM_BASE_ID nie ustawiony"},
                status_code=400
            )

        records = read_excel()

        if dry_run:
            return {
                "dry_run": True,
                "total_records": len(records),
                "message": "DRY RUN - brak zmian w bazie",
            }

        result = seed_records(records, DEFAULT_NC_TOKEN, DEFAULT_NC_URL, DEFAULT_NC_BASE_ID)
        result["dry_run"] = False
        return result

    except Exception as e:
        return JSONResponse(
            {"error": str(e), "type": type(e).__name__},
            status_code=500
        )


@app.post("/seed-upload")
async def seed_upload(
    file: UploadFile = File(...),
    nc_url: str = Query(DEFAULT_NC_URL),
    nc_token: str = Query(DEFAULT_NC_TOKEN),
    nc_base_id: str = Query(DEFAULT_NC_BASE_ID),
    dry_run: bool = Query(True),
):
    """Upload + Seeding - dla formularza n8n/klienta."""
    try:
        if not nc_token or not nc_base_id:
            return JSONResponse(
                {"error": "nc_token lub nc_base_id brak"},
                status_code=400
            )

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            wb = openpyxl.load_workbook(tmp_path)
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

            if dry_run:
                return {
                    "dry_run": True,
                    "file_name": file.filename,
                    "total_records": len(records),
                    "message": "DRY RUN - brak zmian w bazie",
                    "preview": [
                        {
                            "nazwa": rec.get("Nazwa klienta"),
                            "email": rec.get("E.mail"),
                            "typ": rec.get("B2B / B2C"),
                        }
                        for rec in records[:5]
                    ],
                }

            result = seed_records(records, nc_token, nc_url, nc_base_id)
            result["dry_run"] = False
            result["file_name"] = file.filename
            return result

        finally:
            Path(tmp_path).unlink(missing_ok=True)

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
            "GET /preview": "Podgląd danych z Excela (fixed file)",
            "POST /seed?dry_run=true": "Seeding fixed file (preview)",
            "POST /seed?dry_run=false": "Seeding fixed file (pełna migracja)",
            "POST /seed-upload": "Upload file + seeding (dla n8n formularza)",
        },
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
