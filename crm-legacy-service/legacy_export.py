"""Eksport danych CRM z PostgreSQL do pliku w formacie starego CRM.

Odwrotnosc legacy_import.py. Kontrakt, na ktorym polegaja finanse i analiza:
  - kolumna ID to numer z rejestru legacy.rows: raz nadany, nigdy nie zmieniany
    i nie uzywany ponownie; rekordy z nowego CRM dostaja numer z sekwencji przy
    PIERWSZYM eksporcie i rejestr go zapamietuje (dlatego eksport zapisuje do
    rejestru - tylko tam, dane CRM zostaja nietkniete),
  - naglowek i kolejnosc kolumn sa takie jak w ostatnio zaimportowanym pliku
    (legacy.meta 'header'); bez importu - uklad klienta (33 kolumny),
  - jeden wiersz = jeden wiersz Excela: szansa sprzedazy albo lead bez szansy;
    lead, ktory dostal szanse po imporcie, zachowuje swoj numer,
  - daty M/D/YYYY bez zer, godzina "H:MM:SS AM/PM", kwoty "3,900.00 PLN",
    UTF-8 z BOM, CRLF, wiersze od najwyzszego ID.
Pola, ktore import dopisal do notatek leada ("Planowane dzialanie (stary CRM):
..." itd.), wracaja do swoich kolumn, a Notatki zostaja czyste. Nazwy zastepcze
osob ("Nieznany kontakt ...") wracaja jako puste komorki.
"""
import csv
import io
import json
import re
from datetime import datetime
from decimal import Decimal

import legacy_import as li
from legacy_import import C, N_ROW, SCHEMA, TZ, header_key, ident, kept_prefix

# naglowek klienta, gdy nic jeszcze nie zaimportowano (jeden wiersz, komorki z
# nowymi liniami)
DEFAULT_HEADER = [[
    "ID", "Nazwa klienta", "Organizacja", "B2B / B2C", "Handlowiec", "Branża",
    "Źródło", "Forma\nkontaktu", "Kwalifikacja lead'a",
    "Powód braku kwalifikacji lead'a", "Osoba kontaktowa", "Nr telefonu",
    "E.mail", "Data\nwpłynięcia", "Godzina\nwpłynięcia",
    "Data utworzenia klienta", "Data szansy sprzedaży", "Data badania potrzeb",
    "Data\nDEMO", "Data wysłania oferty", "Data omówienia oferty",
    "Data wysłania umowy", "Data podpisania umowy", "Data\nutracenia",
    "Powód utraty szansy", "Etap", "Stan", "Data planowanego działania",
    "Planowane działanie", "Szansa sprzedaży \nWartość",
    "Szansa sprzedaży . Etykieta", "Notatki", "Spr. ID"]]

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

# linie notatek leada -> kolumna (to, co import dopisuje, gdy nie ma gdzie zapisac)
NOTE_PREFIXES = {
    "planned_d": "Data planowanego działania (stary CRM): ",
    "planned": "Planowane działanie (stary CRM): ",
    "label": "Etykieta szansy (stary CRM): ",
    "check_id": "Spr. ID (stary CRM): ",
    "industry": kept_prefix("branża"), "source": kept_prefix("źródło"),
    "channel": kept_prefix("forma kontaktu"), "qualification": kept_prefix("kwalifikacja"),
    **{k: kept_prefix(li.HEADERS[k][0]) for k in (
        "folder", "archived", "value", "received_d", "client_created", "opp_created",
        "needs", "demo", "offer_sent", "offer_discussed", "contract_sent",
        "contract_signed", "lost_d")}}
LOST_RE = re.compile(r"^Utracone w starym CRM(?: (\d{4}-\d{2}-\d{2}))?: (.*)$")
PLACEHOLDER = re.compile(r"^Nieznany kontakt \(stary CRM #\d+\)$")


# ------------------------------------------------------------------ SQL
def _rel(links, name):
    """Podzapytanie (a, b): a = id strony wlasciciela relacji, b = id celu."""
    L = links[name]
    if L["kind"] == "junction":
        return (f"SELECT {ident(L['owner'])} AS a, {ident(L['other'])} AS b "
                f"FROM {SCHEMA}.{ident(L['table'])}")
    table, col = f"{SCHEMA}.{ident(L['table'])}", ident(L["col"])
    if L["on_owner"]:
        return f"SELECT id AS a, {col} AS b FROM {table} WHERE {col} IS NOT NULL"
    return f"SELECT {col} AS a, id AS b FROM {table} WHERE {col} IS NOT NULL"


def _one(links, name):
    """Jedna wartosc b na a (relacje sa 1:1 / n:1)."""
    return f"(SELECT DISTINCT ON (a) a, b FROM ({_rel(links, name)}) t ORDER BY a, b)"


def assign_sql(links):
    """Numery dla rekordow, ktorych nie ma jeszcze w rejestrze (jedna transakcja).
    A: lead bez szansy, ktory dostal szanse po imporcie, zachowuje swoj numer.
    B: pozostale szanse dostaja kolejne numery. C: leady bez szansy i bez numeru."""
    s, reg = SCHEMA, li.REGISTRY
    opp_lead = _one(links, "opp_source_lead")
    return f"""BEGIN;
UPDATE {reg} r SET opportunity_id = n.opp_id
FROM (SELECT DISTINCT ON (ol.b) ol.b AS lead_id, o.id AS opp_id
      FROM {s}.sale_opportunities o JOIN {opp_lead} ol ON ol.a = o.id
      WHERE NOT EXISTS (SELECT 1 FROM {reg} x WHERE x.opportunity_id = o.id)
      ORDER BY ol.b, o.created_at, o.id) n
WHERE r.lead_id = n.lead_id AND r.opportunity_id IS NULL;
INSERT INTO {reg} (export_id, lead_id, opportunity_id, source)
SELECT nextval('legacy.export_id_seq'), q.lead_id, q.opp_id, 'crm' FROM (
  SELECT ol.b AS lead_id, o.id AS opp_id
  FROM {s}.sale_opportunities o LEFT JOIN {opp_lead} ol ON ol.a = o.id
  WHERE NOT EXISTS (SELECT 1 FROM {reg} x WHERE x.opportunity_id = o.id)
  ORDER BY o.created_at, o.id) q;
INSERT INTO {reg} (export_id, lead_id, opportunity_id, source)
SELECT nextval('legacy.export_id_seq'), q.id, NULL, 'crm' FROM (
  SELECT l.id FROM {s}.leads l
  WHERE NOT EXISTS (SELECT 1 FROM {reg} x WHERE x.lead_id = l.id)
  ORDER BY l.received_at, l.id) q;
COMMIT;
"""


def data_query(links):
    s = SCHEMA
    hist_opp = _rel(links, "history_opp")
    return f"""
WITH lp AS {_one(links, "lead_primary_person")}, lc AS {_one(links, "lead_company")},
     lo AS {_one(links, "lead_owner")}, op AS {_one(links, "opp_person")},
     oc AS {_one(links, "opp_company")}, oo AS {_one(links, "opp_owner")},
     hist AS (
       SELECT g.opp_id, jsonb_object_agg(g.to_stage, g.at) AS h FROM (
         SELECT hj.b AS opp_id, h.to_stage, min(h.changed_at) AS at
         FROM {s}.sale_opportunity_stage_history h
         JOIN ({hist_opp}) hj ON hj.a = h.id GROUP BY hj.b, h.to_stage) g
       GROUP BY g.opp_id)
SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.export_id DESC), '[]'::jsonb)::text FROM (
  SELECT r.export_id, r.orig,
         l.lead_name, l.lead_type, l.lead_source, l.contact_channel,
         l.qualification, l.disqualify_note, l.received_at, l.notes,
         p.full_name AS p_name, p.email AS p_email, p.phone AS p_phone,
         p.industry AS p_industry, p.created_at AS p_created,
         c.name AS c_name, c.industry AS c_industry,
         e.id AS seller_id, e.full_name AS seller_name,
         o.id AS opp_id, o.name AS opp_name, o.segment AS opp_segment,
         o.stage, o.state, o.loss_note, o.loss_reason, o.deal_value,
         o.created_at AS opp_created, h.h AS hist
  FROM {li.REGISTRY} r
  LEFT JOIN {s}.leads l ON l.id = r.lead_id
  LEFT JOIN {s}.sale_opportunities o ON o.id = r.opportunity_id
  LEFT JOIN lp ON lp.a = l.id LEFT JOIN op ON op.a = o.id
  LEFT JOIN {s}.persons p ON p.id = coalesce(lp.b, op.b)
  LEFT JOIN lc ON lc.a = l.id LEFT JOIN oc ON oc.a = o.id
  LEFT JOIN {s}.companies c ON c.id = coalesce(lc.b, oc.b)
  LEFT JOIN lo ON lo.a = l.id LEFT JOIN oo ON oo.a = o.id
  LEFT JOIN {s}.employees e ON e.id = coalesce(lo.b, oo.b)
  LEFT JOIN hist h ON h.opp_id = o.id
  WHERE l.id IS NOT NULL OR o.id IS NOT NULL
) x
"""


# ------------------------------------------------------------- formatting
def _ts(v):
    return datetime.fromisoformat(v).astimezone(TZ) if v else None


def _d(ts):
    return f"{ts.month}/{ts.day}/{ts.year}" if ts else ""


def _time(ts):
    if not ts or (ts.hour, ts.minute, ts.second) == (0, 0, 0):
        return ""
    h = ts.hour % 12 or 12
    return f"{h}:{ts.minute:02d}:{ts.second:02d} {'AM' if ts.hour < 12 else 'PM'}"


def _money(v):
    return f"{Decimal(str(v)):,.2f} PLN"


def _real(name):
    return "" if not name or PLACEHOLDER.match(name) else name


def split_notes(notes):
    """Notatki leada -> (czyste notatki, {kolumna: wartosc}, utrata lub None)."""
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


def to_row(x, export_id, sellers=None):
    """Wiersz w ukladzie C (N_ROW pol). `sellers`: id pracownika -> zapis
    handlowca z pliku wejsciowego."""
    r = [""] * N_ROW
    orig = x.get("orig") or {}
    opp = bool(x.get("opp_id"))
    segment = x.get("lead_type") or x.get("opp_segment") or ""
    b2b = segment == "B2B"
    notes, extra, lost = split_notes(x.get("notes"))
    recv = _ts(x.get("received_at"))
    opp_created = _ts(x.get("opp_created")) if opp else None
    p_created = _ts(x.get("p_created"))
    r[C["id"]] = str(export_id)
    if b2b:
        r[C["client"]] = r[C["org"]] = x.get("c_name") or ""
    else:
        r[C["client"]] = _real(x.get("lead_name") or x.get("opp_name")
                               or x.get("p_name"))
    r[C["segment"]] = segment
    sid = x.get("seller_id")
    r[C["seller"]] = (sellers or {}).get(str(sid)) or x.get("seller_name") or ""
    r[C["industry"]] = (x.get("c_industry") or x.get("p_industry")
                        or extra.get("industry", ""))
    r[C["source"]] = x.get("lead_source") or extra.get("source", "")
    r[C["channel"]] = x.get("contact_channel") or extra.get("channel", "")
    r[C["qualification"]] = x.get("qualification") or extra.get("qualification", "")
    r[C["disq_reason"]] = x.get("disqualify_note") or ""
    r[C["contact"]] = _real(x.get("p_name"))
    r[C["phone"]] = x.get("p_phone") or ""
    r[C["email"]] = x.get("p_email") or ""

    # data wplyniecia: import bierze date szansy, gdy pliku jej brakowalo - wtedy
    # (i dopoki lead sie nie zmienil) komorka zostaje pusta jak w pliku
    derived_recv = (orig and not orig.get("received_d") and recv and opp_created
                    and recv.date() == opp_created.date())
    if recv and not derived_recv:
        r[C["received_d"]] = _d(recv)
        r[C["received_t"]] = _time(recv)
    else:
        r[C["received_d"]] = extra.get("received_d", "")
    show_client = p_created and (bool(orig.get("client_created")) or not recv
                                 or p_created.date() != recv.date())
    r[C["client_created"]] = _d(p_created) if show_client else extra.get("client_created", "")

    hist = x.get("hist") or {}
    if opp:
        if not (orig and not orig.get("opp_created")):
            r[C["opp_created"]] = _d(opp_created)
        for stage, key in MILESTONE.items():
            if hist.get(stage):
                r[C[key]] = _d(_ts(hist[stage]))
        r[C["stage"]] = STAGE_OUT.get(x["stage"], "")
        r[C["state"]] = STATE_OUT.get(x["state"], "")
        if x["state"] == "lost":
            r[C["loss_reason"]] = x.get("loss_note") or x.get("loss_reason") or ""
        if x.get("deal_value") not in (None, ""):
            r[C["value"]] = _money(x["deal_value"])
    else:
        r[C["state"]] = "Utracona" if lost else "Otwarta"
        if lost:
            r[C["stage"]] = "utracona"
            r[C["lost_d"]] = (_d(datetime.fromisoformat(lost[0]).replace(tzinfo=TZ))
                              if lost[0] else "")
            r[C["loss_reason"]] = lost[1] if lost[1] != "bez powodu" else ""
    # wartosci, ktorych importer nie umial zapisac (nieczytelne daty itd.)
    for key in ("opp_created", "needs", "demo", "offer_sent", "offer_discussed",
                "contract_sent", "contract_signed", "lost_d", "planned_d", "planned",
                "label", "check_id", "folder", "archived", "value"):
        if not r[C[key]]:
            r[C[key]] = extra.get(key, "")
    r[C["notes"]] = notes
    return r


# ------------------------------------------------------------------ export
def load_meta(db):
    header, sellers = None, {}
    for key, value in db.run("SELECT key, value::text FROM legacy.meta", tuples=True):
        if key == "header":
            header = json.loads(value)
        elif key.startswith("seller:"):
            sellers[key[7:]] = json.loads(value)
    return header or DEFAULT_HEADER, sellers


def layout(header_rows):
    """Klucz kolumny (albo None) dla kazdej komorki naglowka."""
    head, sub = header_rows[0], (header_rows[1] if len(header_rows) > 1 else [])
    return [header_key(f"{h} {sub[i] if i < len(sub) else ''}")
            for i, h in enumerate(head)]


def run_export(db, schema_map):
    """Zwraca (bytes_csv, liczba_wierszy). Zapisuje do rejestru legacy.rows numery
    nowych rekordow (jedyny zapis; dane CRM sie nie zmieniaja)."""
    links = li.discover(db, schema_map)
    db.run(assign_sql(links))
    out = db.run(data_query(links), tuples=True)
    items = json.loads(out[0][0], parse_float=Decimal) if out else []
    header, sellers = load_meta(db)
    keys = layout(header)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    for h in header:
        w.writerow(h)
    for x in items:  # od najwyzszego ID
        row = to_row(x, x["export_id"], sellers)
        w.writerow([row[C[k]] if k else "" for k in keys])
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8"), len(items)
