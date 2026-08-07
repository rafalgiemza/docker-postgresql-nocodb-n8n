#!/usr/bin/env python3
"""Seed NocoDB CRM z prawdziwymi danymi ze starego CRM (Excel).

Czyta: Statusy_z_CRM_filled.xlsx (w tym samym folderze)
Tworzy w NocoDB: leads, companies (B2B), participants

Zaktualizowane pod schemat po fable/feedback-tables-1.md (2026-08-06) -
patrz fable/create_offer_tables.py. Wymaga bazy stworzonej TĄ wersją skryptu
(pola `lead_name`/`lead_type`/`lead_source`/`deal_value` na `leads`, nowe
listy opcji `lead_source`/`contact_channel`/`industry`; tabela `participants`
zostaje - klientka potwierdziła, że ta nazwa jest ok).

CO ROBI:
  1. Czyta 1600 rekordów z Excela (bez wymyślania danych)
  2. Mapuje kolumny Excela -> pola NocoDB (stage, lead_source, contact_channel, etc)
  3. Dla każdego rekordu:
     - Tworzy lead (lead_name, email, phone, stage, deal_value, notes...)
     - Dla B2B: tworzy/znajduje firmę, linkuje lead -> company
     - Tworzy participant (osoba kontaktowa), linkuje lead -> participant
  4. Pomija rekordy już istniejące (dedup po legacy_id)
  5. Wartości Excela, które NIE mają odpowiednika w nowych listach opcji
     (np. "Strona www" w Źródle, "Czat" w Formie kontaktu) NIE są na siłę
     wciskane w najbliższy błędny kubełek - pole zostaje puste, a oryginalna
     wartość ze starego CRM ląduje w `notes`, żeby nic nie zgubić.

MAPOWANIA:
  - B2B/B2C -> lead_type
  - Etap -> stage (utracona->lost, umowa podpisana->contract_signed, etc)
  - Stan -> state (otwarta->open, zamknięta->lost)
  - Źródło -> lead_source (Google, Recommendation, LinkedIn, etc - patrz SOURCE_MAP)
  - Forma kontaktu -> contact_channel (Bookings, Mail, Formularz, Telefon - patrz CHANNEL_MAP)
  - Branża -> industry (IT, Transport/Logistics, etc - patrz INDUSTRY_MAP)
  - Szansa sprzedaży Wartość -> deal_value (PLN)

LINKING:
  - leads -> company (dla B2B via field "company")
  - leads -> participants (via field "participants")

WYMAGA W ŚRODOWISKU:
  NC_API_TOKEN      - token z NocoDB (User menu → Tokens)
  NC_CRM_BASE_ID    - ID bazy z URL: nocodb.../nc/<BASE_ID>
  NC_LOCAL_URL      - opcja, default: http://localhost:8081

Usage:
  cd old-crm-based-seed/seed-fake
  set -a; source ../../.env; set +a
  python3 seed_nocodb_from_excel.py --dry-run    # preview
  python3 seed_nocodb_from_excel.py               # pełna migracja
"""
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
import requests

URL = os.environ.get("NC_LOCAL_URL", "http://localhost:8081").rstrip("/")
TOKEN = os.environ.get("NC_API_TOKEN")
BASE_ID = os.environ.get("NC_CRM_BASE_ID")
EXCEL_PATH = Path(__file__).parent / "Statusy_z_CRM_filled.xlsx"

if not EXCEL_PATH.exists():
    sys.exit(f"Plik Excela nie znaleziony: {EXCEL_PATH}")

S = requests.Session()
S.headers.update({"xc-token": TOKEN, "Content-Type": "application/json"})


def api(method, path, **kw):
    r = S.request(method, f"{URL}{path}", timeout=30, **kw)
    if not r.ok:
        sys.exit(f"API error {r.status_code} on {method} {path}: {r.text[:500]}")
    return r.json() if r.text else {}


def resolve_meta():
    """Zwraca mapę table_title -> table_id i link fields."""
    tables = {}
    links = {}  # table_title -> {field_title -> field_id}

    for t in api("GET", f"/api/v2/meta/bases/{BASE_ID}/tables").get("list", []):
        title = t["title"].strip().lower()
        tables[title] = t["id"]
        links[title] = {}

        # Pobierz pola relacji (Links / LinkToAnotherRecord)
        for col in api("GET", f"/api/v2/meta/tables/{t['id']}").get("columns", []):
            if col.get("uidt") in ("Links", "LinkToAnotherRecord"):
                field_title = col["title"].strip().lower()
                links[title][field_title] = col["id"]

    return tables, links


# --- MAPOWANIE EXCELA -> NOCODB
# Kolumny indeksowane (0-based), nagłówki ze strippingiem newlines
EXCEL_COLS = [
    # idx: (header_key, field_in_data_dict)
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
# opcję tam, gdzie nowa lista po prostu nie ma odpowiednika (np. nowa
# lead_source nie ma "strony www"/"kampanii ads"/"targów") - lepiej zostawić
# pole puste i zapisać oryginał w notes niż udawać, że to np. "Google".
# Patrz mapped() w create_lead(): brak klucza w mapie == wartość leci do notes.
SOURCE_MAP = {
    "Google": "Google",
    "Polecenie": "Recommendation",
    "LinkedIn": "LinkedIn",
    "Facebook": "Facebook",
    "Webinar": "Webinar",
    "Cold mail": "Outreach",  # cold mail to forma outreachu, sensowne 1:1
    # BEZ mapowania (-> notes): "Strona www", "Kampania Ads", "Targi" - nowa
    # lista (Google/Outreach/Existing client/LinkedIn/Recommendation/Webinar/
    # Facebook/Coming back Lead/Coming back Client) nie ma odpowiednika.
}

CHANNEL_MAP = {
    "Bookings": "Bookings",
    "E-mail": "Mail",
    "Formularz WWW": "Formularz",
    "Telefon": "Telefon",
    # BEZ mapowania (-> notes): "Czat", "Spotkanie" - nowa lista nie ma
    # "chat"/"spotkanie osobiste"; stare fallbacki (Czat->email, Spotkanie->
    # telefon) fałszowały dane, więc usunięte.
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
    "badanie potrzeb": "audit",  # discovery potrzeb = audit
    "demo": "discovery_done",
    "oferta wysłana": "offer_sent",
    "omówienie oferty": "offer_discussed",
    "umowa wysłana": "contract_sent",
    "umowa podpisana": "contract_signed",
    "utracona": "lost",
    "brak kwalifikacji": "new",  # niezkwalifikowany wraca na new
}

STATE_MAP = {
    "otwarta": "open",
    "zamknięta": "lost",  # stan stary: zamknięta = koniec życia
}

LOSS_REASON_MAP = {
    "Cena": "cena",
    "Brak decyzji": "brak_decyzji",
    "Konkurencja": "konkurencja",
    "Przesunięte w czasie": "przesuniete_w_czasie",
}


def parse_date(val):
    """Konwertuje datę z Excela na ISO string."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val.date().isoformat()
    if isinstance(val, str):
        # Spróbuj parsować jako "YYYY-MM-DD"
        try:
            return datetime.strptime(val, "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None
    return None


def map_value(value, mapping, default=None):
    """Mapuje wartość z Excela -> wartość NocoDB."""
    if not value:
        return default
    value_str = str(value).strip()
    # Próbuj dokładne dopasowanie
    if value_str in mapping:
        return mapping[value_str]
    # Próbuj case-insensitive
    for key, mapped in mapping.items():
        if key.lower() == value_str.lower():
            return mapped
    return default


def read_excel():
    """Czyta Excel i zwraca listę słowników (jeden rekord = jeden lead)."""
    wb = openpyxl.load_workbook(EXCEL_PATH)
    ws = wb.active

    records = []
    for row in ws.iter_rows(min_row=2, values_only=False):
        # Odczytaj wartości po indeksie kolumny
        data = {}
        for col_idx, field_key in EXCEL_COLS:
            if col_idx < len(row):
                data[field_key] = row[col_idx].value

        # Przesłanki do pominięcia
        if not data.get("Nazwa klienta"):
            continue

        records.append(data)

    return records


def create_or_find_company(table_id, name, industry=None):
    """Szuka czy tworzy firmę (B2B). Zwraca company id."""
    if not name or not name.strip():
        return None

    # Szukaj istniejącej
    res = api("GET", f"/api/v2/tables/{table_id}/records",
              params={"where": f"(name,like,%{name}%)"})
    existing = res.get("list", [])
    if existing:
        return existing[0].get("Id")

    # Utwórz nową
    record = {"name": name.strip()}
    if industry:
        mapped_industry = map_value(industry, INDUSTRY_MAP)
        if mapped_industry:
            record["industry"] = mapped_industry
        else:
            record["notes"] = f"Branża (stary CRM): {str(industry).strip()}"

    res = api("POST", f"/api/v2/tables/{table_id}/records", json=record)
    return res.get("Id") or (res[0].get("Id") if isinstance(res, list) else None)


def create_lead(tables, excel_data):
    """Tworzy rekord leada z danych Excela. Zwraca lead_id."""
    unmapped = []  # wartości ze starego CRM bez odpowiednika w nowych listach

    def mapped(value, mapping, field_label):
        result = map_value(value, mapping)
        if value and not result:
            unmapped.append(f"{field_label} (stary CRM): {str(value).strip()}")
        return result

    lead_data = {
        "lead_name": (excel_data.get("Nazwa klienta") or "").strip(),
        "contact_email": (excel_data.get("E.mail") or "").strip() or None,
        "contact_phone": (excel_data.get("Nr telefonu") or "").strip() or None,
        "lead_type": excel_data.get("B2B / B2C", "B2C"),
        "lead_source": mapped(excel_data.get("Źródło"), SOURCE_MAP, "Źródło"),
        "contact_channel": mapped(excel_data.get("Forma kontaktu"), CHANNEL_MAP, "Forma kontaktu"),
        "qualification": mapped(excel_data.get("Kwalifikacja lead'a"), QUALIFICATION_MAP, "Kwalifikacja"),
        "disqualify_reason": map_value(
            excel_data.get("Powód braku kwalifikacji lead'a"),
            LOSS_REASON_MAP),
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

    # Oryginalne notatki + wartości ze starego CRM, które nie zmapowały się
    # na nową liste opcji (patrz mapped() wyzej) - zeby nic nie zgubic.
    notes_parts = [(excel_data.get("Notatki") or "").strip()] + unmapped
    lead_data["notes"] = "\n".join(p for p in notes_parts if p) or None

    # Usuń None i puste stringi
    lead_data = {k: v for k, v in lead_data.items() if v is not None and v != ""}

    res = api("POST", f"/api/v2/tables/{tables['leads']}/records", json=lead_data)
    return res.get("Id") or (res[0].get("Id") if isinstance(res, list) else None)


def link_records(table_name, field_name, record_id, target_ids, tables, links, dry_run=False):
    """Linkuje rekordy. Zwraca True jeśli sukces, False jeśli field nie istnieje."""
    if not target_ids:
        return True
    if not isinstance(target_ids, list):
        target_ids = [target_ids]
    if not target_ids or not record_id:
        return True

    table_name_lower = table_name.lower()
    field_name_lower = field_name.lower()

    # Szukaj field ID
    if table_name_lower not in links:
        print(f"    ⚠ tabela '{table_name}' nie znaleziona w link fields")
        return False

    field_id = links[table_name_lower].get(field_name_lower)
    if not field_id:
        available = list(links.get(table_name_lower, {}).keys())
        print(f"    ⚠ pole '{field_name}' nie znalezione w '{table_name}' "
              f"(dostępne: {available})")
        return False

    if dry_run:
        print(f"    ~ {table_name}#{record_id}.{field_name} -> {target_ids}")
        return True

    # Linkuj
    api("POST", f"/api/v2/tables/{tables[table_name_lower]}/links/{field_id}/records/{record_id}",
        json=[{"Id": i} for i in target_ids if i])
    return True


def main(dry_run=False):
    if not dry_run:
        if not TOKEN or not BASE_ID or TOKEN == "API_TOKEN_PLACEHOLDER":
            sys.exit("Brak NC_API_TOKEN / NC_CRM_BASE_ID w środowisku - patrz .env.example.")

    print(f"NocoDB: {URL}, base: {BASE_ID}{' [DRY RUN]' if dry_run else ''}\n")

    if dry_run:
        tables = {"leads": 1, "companies": 2, "participants": 3}  # dummy
        links = {}
    else:
        tables, links = resolve_meta()
        print(f"Tabele: {list(tables.keys())}\n")
        print(f"Link fields w leads: {links.get('leads', {})}\n")
        if not all(t in tables for t in ["leads", "companies", "participants"]):
            sys.exit("Brakuje tabel: leads, companies, participants")

    print("Czytam Excel...")
    records = read_excel()
    print(f"Wczytano {len(records)} rekordów\n")

    if dry_run:
        print("[DRY RUN] Pokazuję pierwsze 3 rekordy:")
        for i, rec in enumerate(records[:3], 1):
            print(f"\n  {i}. {rec.get('Nazwa klienta')} ({rec.get('B2B / B2C')})")
            print(f"     Email: {rec.get('E.mail')}")
            print(f"     Etap: {rec.get('Etap')}")
        print(f"\n[DRY RUN] Razem: {len(records)} rekordów do przetworzenia")
        return

    created_leads = 0
    created_companies = 0
    created_participants = 0
    skipped = 0

    for idx, rec in enumerate(records, 1):
        try:
            legacy_id = str(rec.get("Spr. ID") or "").strip()
            contact_name = (rec.get("Nazwa klienta") or "").strip()

            # Sprawdź, czy taki lead już istnieje (legacy_id)
            if legacy_id:
                existing = api("GET", f"/api/v2/tables/{tables['leads']}/records",
                             params={"where": f"(legacy_id,eq,{legacy_id})"})
                if existing.get("list"):
                    skipped += 1
                    continue

            # Utwórz lead
            lead_id = create_lead(tables, rec)
            if not lead_id:
                print(f"  ! {contact_name}: nie udało się utworzyć leada")
                skipped += 1
                continue
            created_leads += 1

            # Dla B2B: utwórz/link firmę
            if rec.get("B2B / B2C") == "B2B":
                org_name = rec.get("Organizacja")
                if org_name and org_name.strip():
                    company_id = create_or_find_company(
                        tables["companies"],
                        org_name,
                        rec.get("Branża"))
                    if company_id:
                        created_companies += 1
                        # Linkuj lead -> company
                        link_records("leads", "company", lead_id, company_id,
                                   tables, links, dry_run=False)

            # Utwórz participant (osoba kontaktowa)
            participant_data = {
                "full_name": contact_name,
                "email": (rec.get("E.mail") or "").strip() or None,
            }
            participant_data = {k: v for k, v in participant_data.items() if v}

            p_res = api("POST", f"/api/v2/tables/{tables['participants']}/records",
                       json=participant_data)
            participant_id = p_res.get("Id") or (p_res[0].get("Id") if isinstance(p_res, list) else None)
            if participant_id:
                created_participants += 1
                # Linkuj lead -> participant
                link_records("leads", "participants", lead_id, participant_id,
                           tables, links, dry_run=False)

            if idx % 100 == 0:
                print(f"  {idx}/{len(records)} ...")

        except Exception as e:
            print(f"  ! {contact_name}: {e}")
            skipped += 1
            continue

    print(f"\n✓ Leads: {created_leads}")
    print(f"✓ Companies: {created_companies}")
    print(f"✓ Participants: {created_participants}")
    print(f"⊘ Skipped/errors: {skipped}")
    print(f"\nRazem: {created_leads + created_companies + created_participants} rekordów")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="pokaż plan, nie wywoływaj API")
    args = ap.parse_args()

    main(dry_run=args.dry_run)
