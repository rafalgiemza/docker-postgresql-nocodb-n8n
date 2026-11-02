"""Eksport danych CRM z PostgreSQL do pliku w formacie starego CRM.

Odwrotnosc legacy_import.py: te same 32 kolumny, dwa wiersze naglowka jak w
oryginale, daty MM/DD/YYYY, godzina "H:MM:SS AM/PM", UTF-8, CRLF. Jeden wiersz
na lead; dane szansy (etap, daty kamieni milowych z historii etapow) dokladane
gdy lead ma szanse. Pisze WYLACZNIE do pliku - nic nie zmienia w bazie
(decyzja: .ai/rules/nocodb.md, sekcja 6 - eksport/import idzie przez Postgres).

Pola, ktore import dopisal do notatek leada ("Planowane dzialanie (stary CRM):
..." itd.), wracaja do swoich kolumn, a Notatki zostaja czyste.
"""
import csv
import io
import json
import re
from datetime import datetime

import legacy_import as li
from legacy_import import C, N_COLS, SCHEMA, TZ, ident

# naglowek jak w pliku klienta: jeden wiersz, komorki z nowymi liniami
HEADER = [
    "ID", "Nazwa klienta", "Organizacja", "B2B / B2C", "Handlowiec", "Branża",
    "Źródło", "Forma\nkontaktu", "Kwalifikacja lead'a",
    "Powód braku kwalifikacji lead'a", "Osoba kontaktowa", "Nr telefonu",
    "E.mail", "Data\nwpłynięcia", "Godzina\nwpłynięcia",
    "Data utworzenia klienta", "Data szansy sprzedaży", "Data badania potrzeb",
    "Data\nDEMO", "Data wysłania oferty", "Data omówienia oferty",
    "Data wysłania umowy", "Data podpisania umowy", "Data\nutracenia",
    "Powód utraty szansy", "Etap", "Stan", "Data planowanego działania",
    "Planowane działanie", "Szansa sprzedaży \nWartość",
    "Szansa sprzedaży . Etykieta", "Notatki", "Spr. ID"]

# stage v4 -> "Etap" starego CRM (odwrotnosc STAGE_MAP; "Nowa" i etapy
# discovery nie maja odpowiednika w starym CRM)
STAGE_OUT = {
    "Audyt": "badanie potrzeb", "Rekomendacja / demo": "demo",
    "Oferta wysłana": "wysłanie oferty", "Omówienie oferty": "omówienie oferty",
    "Umowa wysłana": "wysłanie umowy", "Umowa podpisana": "umowa podpisana",
    "Utracona": "utracona"}
STATE_OUT = {"open": "Otwarta", "won": "Zamknięta", "lost": "Utracona"}
# stage historii -> kolumna z data kamienia milowego
MILESTONE = {"Audyt": "needs", "Rekomendacja / demo": "demo",
             "Oferta wysłana": "offer_sent", "Omówienie oferty": "offer_discussed",
             "Umowa wysłana": "contract_sent", "Umowa podpisana": "contract_signed",
             "Utracona": "lost_d"}

NOTE_PREFIXES = {
    "planned_d": "Data planowanego działania (stary CRM): ",
    "planned": "Planowane działanie (stary CRM): ",
    "label": "Etykieta szansy (stary CRM): ",
    "check_id": "Spr. ID (stary CRM): "}
LOST_RE = re.compile(r"^Utracone w starym CRM(?: (\d{4}-\d{2}-\d{2}))?: (.*)$")


def _link_sql(links, schema_map, name, owner, reverse=False):
    """Podzapytanie zwracajace id wiersza docelowego relacji `name` dla wiersza
    `owner` (wyrazenie SQL z id strony wlasciciela). reverse=True: szukamy
    wlasciciela dla zadanego celu."""
    L = links[name]
    table, field = li.LINKS[name]
    related = schema_map[table]["fields"][field]["related_table"]
    if L["kind"] == "junction":
        t, o, c = (f"{SCHEMA}.{ident(L['table'])}", ident(L["owner"]), ident(L["other"]))
        if reverse:
            return f"(SELECT {o} FROM {t} WHERE {c} = {owner} LIMIT 1)"
        return f"(SELECT {c} FROM {t} WHERE {o} = {owner} LIMIT 1)"
    col = ident(L["col"])
    if L["on_owner"]:
        return (f"(SELECT id FROM {SCHEMA}.{table} WHERE {col} = {owner} LIMIT 1)" if reverse
                else f"(SELECT {col} FROM {SCHEMA}.{table} WHERE id = {owner})")
    return (f"(SELECT {col} FROM {SCHEMA}.{related} WHERE id = {owner})" if reverse
            else f"(SELECT id FROM {SCHEMA}.{related} WHERE {col} = {owner} LIMIT 1)")


def build_query(links, schema_map):
    s = SCHEMA
    person = _link_sql(links, schema_map, "lead_primary_person", "l.id")
    company = _link_sql(links, schema_map, "lead_company", "l.id")
    owner = _link_sql(links, schema_map, "lead_owner", "l.id")
    opp = _link_sql(links, schema_map, "opp_source_lead", "l.id", reverse=True)
    hist_ids = _link_sql(links, schema_map, "history_opp", "h.id")
    return f"""
SELECT coalesce(jsonb_agg(x ORDER BY x.received_at, x.lead_id), '[]'::jsonb)::text FROM (
  SELECT l.id AS lead_id,
         (SELECT r.export_id FROM legacy.rows r WHERE r.lead_id = l.id
          ORDER BY r.export_id LIMIT 1) AS legacy_id, l.lead_name, l.lead_type, l.lead_source,
         l.contact_channel, l.qualification, l.disqualify_note, l.received_at,
         l.notes,
         p.full_name AS p_name, p.email AS p_email, p.phone AS p_phone,
         p.industry AS p_industry, p.created_at AS p_created,
         c.name AS c_name, c.industry AS c_industry,
         e.full_name AS seller,
         o.id AS opp_id, o.stage, o.state, o.loss_note, o.loss_reason,
         o.deal_value, o.created_at AS opp_created,
         (SELECT json_object_agg(s.to_stage, s.at) FROM (
            SELECT h.to_stage, min(h.changed_at) AS at
            FROM {s}.sale_opportunity_stage_history h
            WHERE {hist_ids} = o.id
            GROUP BY h.to_stage) s) AS hist
  FROM {s}.leads l
  LEFT JOIN {s}.persons p ON p.id = {person}
  LEFT JOIN {s}.companies c ON c.id = {company}
  LEFT JOIN {s}.employees e ON e.id = {owner}
  LEFT JOIN {s}.sale_opportunities o ON o.id = {opp}
) x
"""


def _ts(v):
    return datetime.fromisoformat(v).astimezone(TZ) if v else None


def _d(ts):
    return ts.strftime("%m/%d/%Y") if ts else ""


def _time(ts):
    if not ts or (ts.hour, ts.minute, ts.second) == (0, 0, 0):
        return ""
    h = ts.hour % 12 or 12
    return f"{h}:{ts.minute:02d}:{ts.second:02d} {'AM' if ts.hour < 12 else 'PM'}"


def split_notes(notes):
    """Notatki leada -> (czyste notatki, planned, label, check_id, lost)."""
    keep, extra, lost = [], {}, None
    for line in (notes or "").split("\n"):
        for key, pre in NOTE_PREFIXES.items():
            if line.startswith(pre):
                extra[key] = line[len(pre):]
                break
        else:
            m = LOST_RE.match(line)
            if m:
                lost = (m.group(1), m.group(2))
            else:
                keep.append(line)
    return "\n".join(keep).strip(), extra, lost


def to_row(x, legacy_id):
    r = [""] * N_COLS
    b2b = x["lead_type"] == "B2B"
    notes, extra, lost = split_notes(x.get("notes"))
    recv = _ts(x["received_at"])
    r[C["id"]] = str(legacy_id)
    if b2b:
        r[C["client"]] = r[C["org"]] = x.get("c_name") or ""
    else:
        r[C["client"]] = x.get("lead_name") or x.get("p_name") or ""
    r[C["segment"]] = x["lead_type"] or ""
    seller = (x.get("seller") or "").split(" ")[0]
    r[C["seller"]] = seller
    r[C["industry"]] = (x.get("c_industry") if b2b else x.get("p_industry")) or ""
    r[C["source"]] = x.get("lead_source") or ""
    r[C["channel"]] = x.get("contact_channel") or ""
    r[C["qualification"]] = x.get("qualification") or ""
    r[C["disq_reason"]] = x.get("disqualify_note") or ""
    r[C["contact"]] = x.get("p_name") or ""
    r[C["phone"]] = x.get("p_phone") or ""
    r[C["email"]] = x.get("p_email") or ""
    r[C["received_d"]] = _d(recv)
    r[C["received_t"]] = _time(recv)
    hist = x.get("hist") or {}
    if x.get("opp_id"):
        r[C["client_created"]] = _d(_ts(x.get("p_created")))
        r[C["opp_created"]] = _d(_ts(x["opp_created"]))
        for stage, key in MILESTONE.items():
            if hist.get(stage):
                r[C[key]] = _d(_ts(hist[stage]))
        r[C["stage"]] = STAGE_OUT.get(x["stage"], "")
        r[C["state"]] = STATE_OUT.get(x["state"], "")
        if x["state"] == "lost":
            r[C["loss_reason"]] = x.get("loss_note") or x.get("loss_reason") or ""
        if x.get("deal_value") not in (None, ""):
            r[C["value"]] = str(x["deal_value"]).replace(".", ",")
    else:
        r[C["state"]] = "Utracona" if lost else "Otwarta"
        if lost:
            r[C["stage"]] = "utracona"
            r[C["lost_d"]] = _d(datetime.fromisoformat(lost[0]).replace(tzinfo=TZ)) if lost[0] else ""
            r[C["loss_reason"]] = lost[1] if lost[1] != "bez powodu" else ""
    r[C["planned_d"]] = extra.get("planned_d", "")
    r[C["planned"]] = extra.get("planned", "")
    r[C["label"]] = extra.get("label", "")
    r[C["check_id"]] = extra.get("check_id", "")
    r[C["notes"]] = notes
    return r


def run_export(db, schema_map):
    """Zwraca (bytes_csv, liczba_wierszy). Tylko SELECT."""
    links = li.discover(db, schema_map)
    out = db.run(build_query(links, schema_map), tuples=True)
    leads = json.loads(out[0][0]) if out else []
    # ID ze starego CRM; leady powstale juz w nowym CRM dostaja kolejne numery
    next_id = max([x["legacy_id"] or 0 for x in leads] + [0])
    rows = []
    for x in leads:  # posortowane po received_at
        lid = x["legacy_id"]
        if not lid:
            next_id += 1
            lid = next_id
        rows.append((int(lid), to_row(x, lid)))
    rows.sort(key=lambda t: -t[0])
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(HEADER)
    for _id, r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8"), len(rows)
