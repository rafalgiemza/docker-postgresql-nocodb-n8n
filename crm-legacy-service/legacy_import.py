"""Logika importu historycznych rekordow ze starego CRM (CSV) wprost do PostgreSQL.

WYJATEK OD ZASADY "dane przez NocoDB": NocoDB nie pozwala ustawic created_at,
a tu zalezy nam na prawdziwych datach (wplyniecie leada, utworzenie klienta,
kamienie milowe szansy). Decyzja: .ai/rules/nocodb.md, sekcja 6.

Odpowiednik W4v4 (docs/archive/fable/W4v4_form_intake.json) dla rekordow
historycznych. Z jednego wiersza CSV powstaja:
  - company (tylko B2B; dedup po nazwie),
  - person (dedup po e-mailu, potem po 9 ostatnich cyfrach telefonu),
  - lead (legacy_id = ID ze starego CRM; to klucz idempotencji),
  - linki: leads.persons (M2M), leads.primary_person, leads.owner,
    leads.company, persons.company,
  - activity `lead_created`,
  - sale_opportunity + sale_opportunity_stage_history, gdy w wierszu jest
    "Data szansy sprzedazy" (bez niej wiersz to sam lead - utrata/powod
    laduja w notatkach leada).
Nie uruchamia zadnych flow n8n/NocoDB (brak W2, W20, zadan), dlatego historie
etapow zapisujemy sami.

Linki (leads.company, leads.owner, leads.persons...) w schemacie v4 siedza w
tabelach laczacych `_nc_m2m_*`: ich nazwy bierzemy z schema_map.json, a nazwy
kolumn z kluczy obcych w information_schema (nic nie jest zgadywane; brak FK =
blad z prosba o `\\d`). Gdy tabeli laczacej nie ma, uzywamy zwyklej kolumny FK.

Usage (z korzenia repo, .env wczytany przez make albo zmienne w srodowisku):
  ./scripts/import-crm-legacy.sh docs/crm/crm-utf-8.csv            # DRY-RUN
  ./scripts/import-crm-legacy.sh docs/crm/crm-utf-8.csv --apply    # zapis
Dry-run wykonuje CALOSC w transakcji i ja wycofuje (ROLLBACK), wiec
wychwytuje tez bledy ograniczen bazy. --apply robi COMMIT.

Daty w CSV: MM/DD/YYYY. Jesli tak odczytana data jest pozniejsza niz data
eksportu (--export-date), a odczyt DD/MM jest poprawny i nie pozniejszy,
uzywamy DD/MM (np. 12/10/2026 -> 12 pazdziernika). Kazda zamiana jest
logowana. Godzina wplyniecia: Europe/Warsaw; brak godziny = 00:00, pozostale
daty bez godziny = 12:00 (nie wczesniej niz wplyniecie leada).
"""
import csv
import hashlib
import io
import re
import unicodedata
from datetime import date, datetime, time
from zoneinfo import ZoneInfo


class LegacyError(Exception):
    """Blad, ktory uzytkownik moze naprawic (zle dane / brak tabeli w bazie)."""


def die(msg):
    raise LegacyError(msg)


# Interfejs bazy: obiekt z metoda run(sql, tuples=False) - tuples=True zwraca
# liste list tekstow (SELECT), inaczej tekst z komunikatami NOTICE.
TZ = ZoneInfo("Europe/Warsaw")
SCHEMA = "crm"

# pozycje pol w wierszu po wczytaniu (kolumny pliku dobieramy po nazwie naglowka,
# patrz HEADERS/read_table); kolejnosc 0-32 = uklad klienta/eksportu
C = dict(id=0, client=1, org=2, segment=3, seller=4, industry=5, source=6,
         channel=7, qualification=8, disq_reason=9, contact=10, phone=11,
         email=12, received_d=13, received_t=14, client_created=15,
         opp_created=16, needs=17, demo=18, offer_sent=19, offer_discussed=20,
         contract_sent=21, contract_signed=22, lost_d=23, loss_reason=24,
         stage=25, state=26, planned_d=27, planned=28, value=29, label=30,
         notes=31, check_id=32, folder=33, archived=34)
N_COLS = 33   # szerokosc eksportu (uklad klienta); folder/archived tylko w imporcie
N_ROW = len(C)
BATCH = 50    # wierszy pliku na jeden blok DO (limit pamieci Postgresa)
REGISTRY = "legacy.rows"  # rejestr ID: wiersz Excela -> lead/szansa (make grant-crm-legacy)

# naglowki (male litery, spacje scalone; dwuwierszowy naglowek laczony w jeden)
HEADERS = {
    "id": ["id"], "client": ["nazwa klienta"], "org": ["organizacja"],
    "segment": ["b2b / b2c"], "seller": ["handlowiec"], "industry": ["branża"],
    "source": ["źródło"], "channel": ["forma kontaktu"],
    "qualification": ["kwalifikacja lead'a"],
    "disq_reason": ["powód braku kwalifikacji lead'a"],
    # w zanonimizowanym pliku te trzy kolumny nazywaja sie Kolumna1-3
    "contact": ["osoba kontaktowa", "kolumna1"],
    "phone": ["nr telefonu", "kolumna2"], "email": ["e.mail", "kolumna3"],
    "received_d": ["data wpłynięcia"], "received_t": ["godzina wpłynięcia"],
    "client_created": ["data utworzenia klienta"],
    "opp_created": ["data szansy sprzedaży"], "needs": ["data badania potrzeb"],
    "demo": ["data demo"], "offer_sent": ["data wysłania oferty"],
    "offer_discussed": ["data omówienia oferty"],
    "contract_sent": ["data wysłania umowy"],
    "contract_signed": ["data podpisania umowy"], "lost_d": ["data utracenia"],
    "loss_reason": ["powód utraty szansy"], "stage": ["etap"], "state": ["stan"],
    "planned_d": ["data planowanego działania"], "planned": ["planowane działanie"],
    "value": ["szansa sprzedaży wartość"],
    "label": ["szansa sprzedaży . etykieta"], "notes": ["notatki"],
    "check_id": ["spr. id"], "folder": ["folder klienta"],
    "archived": ["data archiwizacji"]}
HEADER_REQUIRED = ("id", "segment", "received_d", "opp_created")
# kolumny bez miejsca w CRM - zachowane w notatkach leada (eksport je odtworzy)
EXTRA_NOTES = {"folder": "Folder klienta (stary CRM): ",
               "archived": "Data archiwizacji (stary CRM): "}

INDUSTRY = {"Agriculture", "AI", "Automation", "Automotive", "Banking", "Clothing",
            "Construction", "Data Solutions", "Design", "E.commerce", "Energy",
            "Entertainment", "Finance", "Food", "Furniture", "Home Appliances",
            "Hotels", "HR services", "Insurance", "Networks/Itadmin", "IT",
            "Medicine", "Law", "Machinery", "Marketing Agency", "Media", "Pharma",
            "Military", "Packaging", "Public sector", "Publishing", "Real Estate",
            "Retail", "Software Development", "Tech Product", "Telecommunication",
            "Tourism", "Training", "Transport/Logistics", "Housing", "Space",
            "Manufacturing", "Education", "CyberSec"}
LEAD_SOURCE = {"Google", "Outreach", "Existing client", "LinkedIn", "Recommendation",
               "Webinar", "Facebook", "Coming back Lead", "Coming back Client"}
CHANNEL = {"Bookings", "Telefon", "Linkedin CoAction", "Mail", "Formularz",
           "Facebook Przemka", "Facebook CoAction", "Linkedin Przemka"} | LEAD_SOURCE
QUALIFICATION = {"unqualified", "non-MQL", "MQL", "non-SQL", "SQL"}

# "Etap" ze starego CRM -> stage v4 (SALE_STAGES w init-schema.py)
STAGE_MAP = {
    "badanie potrzeb": "Audyt",
    "demo": "Rekomendacja / demo",
    "wysłanie oferty": "Oferta wysłana",
    "oferta wysłana": "Oferta wysłana",
    "omówienie oferty": "Omówienie oferty",
    "wysłanie umowy": "Umowa wysłana",
    "umowa wysłana": "Umowa wysłana",
    "umowa podpisana": "Umowa podpisana",
    "utracona": "Utracona",
}

# kolumny, ktorych uzywamy - sprawdzane w information_schema przed importem
REQUIRED = {
    "companies": ["id", "name", "industry", "created_at"],
    "persons": ["id", "full_name", "email", "phone", "industry", "created_at"],
    "leads": ["id", "lead_name", "lead_type", "lead_source", "contact_channel",
              "qualification", "disqualify_reason", "disqualify_note",
              "received_at", "notes", "created_at"],
    "sale_opportunities": ["id", "name", "segment", "stage", "state", "loss_reason",
                           "loss_note", "deal_value", "offer_sent_at",
                           "contract_sent_at", "closed_at", "stage_changed_at",
                           "notes", "legacy_id", "created_at"],
    "sale_opportunity_stage_history": ["id", "title", "from_stage", "to_stage",
                                       "changed_at", "changed_by", "created_at"],
    "activities": ["id", "summary", "type", "triggered_by", "flow", "payload",
                   "created_at"],
    "employees": ["id", "full_name"],
}
# relacje, ktore zapisujemy: nazwa -> (tabela-wlasciciel, pole w schema_map.json).
# W schemacie v4 (NocoDB "links v2") nawet belongs-to (`mo`) siedzi w tabeli
# laczacej `_nc_m2m_*`, a nie w kolumnie FK - nazwe tabeli bierzemy z
# schema_map.json, nazwy kolumn z kluczy obcych w bazie.
LINKS = {
    "person_company": ("persons", "company"),
    "lead_company": ("leads", "company"),
    "lead_owner": ("leads", "owner"),
    "lead_primary_person": ("leads", "primary_person"),
    "lead_persons": ("leads", "persons"),
    "lead_activities": ("leads", "activities"),
    "opp_person": ("sale_opportunities", "person"),
    "opp_company": ("sale_opportunities", "company"),
    "opp_owner": ("sale_opportunities", "owner"),
    "opp_source_lead": ("sale_opportunities", "source_lead"),
    "history_opp": ("sale_opportunity_stage_history", "sale_opportunity"),
}



def discover(pg, schema_map):
    cols = {}
    for t, c in pg.run(
            f"SELECT table_name, column_name FROM information_schema.columns "
            f"WHERE table_schema='{SCHEMA}'", tuples=True):
        cols.setdefault(t, set()).add(c)
    for t, need in REQUIRED.items():
        if t not in cols:
            die(f"Brak tabeli {SCHEMA}.{t}. Podeslij `\\dt {SCHEMA}.*`.")
        miss = [c for c in need if c not in cols[t]]
        if miss:
            die(f"{SCHEMA}.{t}: brak kolumn {miss}. Podeslij `\\d {SCHEMA}.{t}`.")
    reg = pg.run(f"SELECT to_regclass('{REGISTRY}')", tuples=True)
    if not (reg and reg[0] and reg[0][0]):
        die(f"Brak rejestru ID {REGISTRY}. Uruchom `make grant-crm-legacy`.")
    strip = lambda x: x.split(".")[-1].strip('"')
    fks = {}  # (tabela-z-FK, tabela-docelowa) -> [kolumny]
    for child, col, parent in pg.run(
            f"SELECT c.conrelid::regclass::text, a.attname, c.confrelid::regclass::text "
            f"FROM pg_constraint c JOIN pg_attribute a ON a.attrelid=c.conrelid "
            f"AND a.attnum = ANY(c.conkey) "
            f"JOIN pg_namespace n ON n.oid=c.connamespace "
            f"WHERE c.contype='f' AND n.nspname='{SCHEMA}'", tuples=True):
        fks.setdefault((strip(child), strip(parent)), []).append(col)
    links = {}
    for name, (table, field) in LINKS.items():
        meta = schema_map.get(table, {}).get("fields", {}).get(field)
        if not meta:
            die(f"schema_map.json: brak pola {table}.{field} - odswiez "
                f"`make dump-crm-schema`.")
        related, jt = meta["related_table"], meta.get("junction_table_name")
        single = meta.get("relation_type") in ("mo", "oo", "bt")
        one = lambda pair: fks.get(pair, [])
        if jt in cols:
            a, b = one((jt, table)), one((jt, related))
            if len(a) != 1 or len(b) != 1:
                die(f"{name}: tabela laczaca {SCHEMA}.{jt} - FK do {table}: {a}, "
                    f"do {related}: {b} (oczekiwano po 1). "
                    f"Podeslij `\\d {SCHEMA}.{jt}`.")
            links[name] = dict(kind="junction", table=jt, owner=a[0],
                               other=b[0], single=single)
        elif len(one((table, related))) == 1:
            links[name] = dict(kind="fk", table=table, col=one((table, related))[0],
                               on_owner=True)
        elif len(one((related, table))) == 1:
            links[name] = dict(kind="fk", table=related, col=one((related, table))[0],
                               on_owner=False)
        else:
            die(f"{name}: nie znaleziono ani tabeli {SCHEMA}.{jt}, ani FK "
                f"{table}<->{related}. Podeslij `\\d {SCHEMA}.{table}`.")
    return links


def link(links, name, owner, other):
    """SQL laczacy wiersze (owner = strona pola z schema_map, other = cel)."""
    L = links[name]
    if L["kind"] == "fk":
        if L["on_owner"]:
            return (f"UPDATE {SCHEMA}.{ident(L['table'])} SET {ident(L['col'])} = "
                    f"{other} WHERE id = {owner} AND {ident(L['col'])} IS NULL;")
        return (f"UPDATE {SCHEMA}.{ident(L['table'])} SET {ident(L['col'])} = "
                f"{owner} WHERE id = {other};")
    t, o, c = ident(L["table"]), ident(L["owner"]), ident(L["other"])
    dup = f"{o} = {owner}" + ("" if L["single"] else f" AND {c} = {other}")
    return (f"INSERT INTO {SCHEMA}.{t} ({o}, {c}) SELECT {owner}, {other} "
            f"WHERE NOT EXISTS (SELECT 1 FROM {SCHEMA}.{t} WHERE {dup});")


# ----------------------------------------------------------------- parsing
def q(v):
    if v is None or v == "":
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def _fold(s):
    """male litery, bez ogonkow, lacznik = spacja ('Lasoń-Kurzela' ~ 'Lason Kurzela')."""
    s = unicodedata.normalize("NFKD", s.replace("ł", "l").replace("Ł", "L"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[\s\-]+", " ", s).strip().lower()


def match_employee(seller, employees):
    """id pracownikow pasujacych do 'Handlowiec' z pliku. Najpierw nazwa pelna
    (jedna strona jest poczatkiem drugiej: 'Natalia' ~ 'Natalia Nowak',
    'Agnieszka Lasoń-Kurzela' ~ 'Agnieszka Lasoń'), potem samo imie, ale tylko
    gdy jest jednoznaczne."""
    sf = _fold(seller)
    full = [i for i, n in employees if _fold(n).startswith(sf) or sf.startswith(_fold(n))]
    if full:
        return full
    first = sf.split(" ")[0]
    return [i for i, n in employees if _fold(n).split(" ")[0] == first]


def ident(s):
    return '"' + s.replace('"', '""') + '"'


def parse_date(s, export_date, warn, ctx):
    s = s.strip()
    if not s:
        return None
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    if m:  # recznie wpisane wiersze: DD.MM.YYYY (kropki = zawsze dzien pierwszy)
        try:
            return date(int(m[3]), int(m[2]), int(m[1]))
        except ValueError:
            warn(f"{ctx}: niepoprawna data '{s}' - pominieta")
            return None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if not m:
        warn(f"{ctx}: nieczytelna data '{s}' - pominieta")
        return None
    a, b, y = int(m[1]), int(m[2]), int(m[3])

    def mk(mo, d):
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    mdy, dmy = mk(a, b), mk(b, a)
    if mdy and mdy <= export_date:
        return mdy
    if dmy and dmy <= export_date:
        warn(f"{ctx}: data '{s}' jako MM/DD wypada po eksporcie "
             f"({export_date}) - przyjeto DD/MM = {dmy}")
        return dmy
    if mdy:
        warn(f"{ctx}: data '{s}' = {mdy} jest po dacie eksportu - zostawiona")
        return mdy
    warn(f"{ctx}: niepoprawna data '{s}' - pominieta")
    return None


def at(d, floor=None, hour=12):
    """data -> datetime (Europe/Warsaw), nie wczesniej niz `floor`."""
    if d is None:
        return None
    ts = datetime.combine(d, time(hour), TZ)
    if floor and ts < floor:
        ts = floor
    return ts


def ts_lit(ts):
    return q(ts.isoformat()) if ts else "NULL"


def date_lit(d):
    return q(d.isoformat()) if d else "NULL"


def pick(v, allowed, warn, ctx, label, note=None, aliases=None):
    """Wartosc z listy opcji (bez rozrozniania wielkosci liter i spacji).
    Nieznana wartosc nie ginie: idzie do `note` (notatki leada) i ostrzezenia."""
    v = v.strip()
    if not v:
        return None
    if v in allowed:
        return v
    key = lambda x: re.sub(r"[\s.\-]", "", x).lower()  # 'E-commerce' == 'E.commerce'
    low = {key(a): a for a in allowed}
    if key(v) in low:
        return low[key(v)]
    if key(v) in (aliases or {}):
        return aliases[key(v)]
    warn(f"{ctx}: {label} '{v}' nie ma w opcjach - zapisane tylko w notatkach")
    if note is not None:
        note.append(f"{label[0].upper() + label[1:]} (stary CRM): {v}")
    return None


def disq_reason(text):
    t = text.lower()
    if not t.strip():
        return None
    if "odpowiedzi" in t or "kontakt" in t:
        return "brak_kontaktu"
    if "cena" in t or "budżet" in t or "budzet" in t:
        return "brak_budzetu"
    if "nie chce" in t or "brak potrzeby" in t:
        return "brak_potrzeby"
    if "konkuren" in t:
        return "konkurencja"
    return "inne"


def loss_reason(text):
    t = text.lower()
    if not t.strip():
        return None
    if "price" in t or "cena" in t:
        return "cena"
    if "competitor" in t or "konkuren" in t:
        return "konkurencja"
    if "decision" in t or "decyzj" in t:
        return "brak_decyzji"
    if "later" in t or "timing" in t or "termin" in t or "czas" in t:
        return "przesuniete_w_czasie"
    return "inne"


def money(s):
    """'3,900.00 PLN', '1 234,50 zł', '4800' -> '3900.00' ... (ostatni separator
    to ulamek, o ile ma 1-2 cyfry; reszta to separatory tysiecy)."""
    s = re.sub(r"[^\d,.\-]", "", s.replace("\xa0", ""))
    if not s:
        return None
    m = re.search(r"[.,](\d{1,2})$", s)
    whole, frac = (s[:m.start()], m[1]) if m else (s, "0")
    whole = re.sub(r"[.,]", "", whole)
    try:
        return f"{float(whole + '.' + frac):.2f}"
    except ValueError:
        return None


def decode(data):
    """CSV z Excela bywa w cp1252; probujemy UTF-8, potem cp1252."""
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise LegacyError("Nie mozna odczytac pliku (UTF-8 ani cp1252).")


def _norm(h):
    return re.sub(r"\s+", " ", h).strip().lower()


def read_table(text):
    """(wiersze, uwagi). Wiersze w ukladzie kolumn C (N_ROW pol), kolumny dobrane
    po NAZWIE naglowka - kolejnosc i dodatkowe kolumny nie maja znaczenia.
    Naglowek moze byc jedno- lub dwuwierszowy (drugi wiersz z pustym ID jest
    doklejany do pierwszego); puste kolumny na koncu sa pomijane."""
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if not rows:
        raise LegacyError("Pusty plik.")
    head = list(rows[0])
    body = rows[1:]
    if body and not body[0][:1] == [] and not body[0][0].strip() \
            and any(c.strip() for c in body[0]) \
            and not any(c.strip().isdigit() for c in body[0][:1]):
        head = [f"{h} {body[0][i] if i < len(body[0]) else ''}" for i, h in enumerate(head)]
        body = body[1:]
    head = [_norm(h) for h in head]
    alias = {a: k for k, names in HEADERS.items() for a in names}
    idx, ignored = {}, []
    for i, h in enumerate(head):
        k = alias.get(h)
        if k and k not in idx:
            idx[k] = i
        elif h:
            ignored.append(h)
    miss = [HEADERS[k][0] for k in HEADER_REQUIRED if k not in idx]
    if miss:
        raise LegacyError(
            "W naglowku brak wymaganych kolumn: " + ", ".join(repr(m) for m in miss)
            + ". Znaleziono: " + " | ".join(f"{i + 1}={h!r}" for i, h in enumerate(head) if h))
    out, skipped = [], 0
    for r in body:
        if not any(c.strip() for c in r):
            continue
        if not r[idx["id"]].strip().isdigit():
            skipped += 1  # np. ujemne ID, wiersze zbiorcze
            continue
        row = [""] * N_ROW
        for k, i in idx.items():
            if i < len(r):
                row[C[k]] = r[i]
        out.append(row)
    notes = []
    if ignored:
        notes.append("Kolumny pominięte (brak w CRM): " + ", ".join(sorted(set(ignored))))
    if skipped:
        notes.append(f"Pominięto {skipped} wierszy bez poprawnego dodatniego ID")
    return out, notes


def read_rows(text):
    return read_table(text)[0]


# ---------------------------------------------------------------- generator
def build(rows, links, employees, export_date, warn):
    out = []
    emit = out.append
    seen_ids = set()
    for r in rows:
        r = [x.strip() for x in r] + [""] * (N_ROW - len(r))
        lid = int(r[C["id"]])
        ctx = f"#{lid}"
        if lid in seen_ids:
            warn(f"{ctx}: zdublowane ID w pliku - pominiete")
            continue
        seen_ids.add(lid)

        b2b = r[C["segment"]].upper() == "B2B"
        segment = "B2B" if b2b else "B2C"
        if r[C["segment"]].upper() not in ("B2B", "B2C"):
            warn(f"{ctx}: brak/niepoprawne 'B2B / B2C' - przyjeto B2C")

        # --- osoba / firma
        company = (r[C["org"]] or r[C["client"]]) if b2b else ""
        person_name = (r[C["contact"]] or (r[C["client"]] if not b2b else "")
                       or f"Nieznany kontakt (stary CRM #{lid})")
        lead_name = r[C["client"]] or r[C["org"]] or person_name
        email = r[C["email"]].lower()
        phone = r[C["phone"]]
        core = re.sub(r"\D", "", phone)
        core = core[-9:] if len(core) >= 9 else ""
        kept = []  # wartosci spoza slownikow - zostaja w notatkach leada
        ind = pick(r[C["industry"]], INDUSTRY, warn, ctx, "branża", kept)

        # --- daty
        def pd(k):
            d = parse_date(r[C[k]], export_date, warn, f"{ctx} {k}")
            if d is None and r[C[k]]:  # nieczytelna wartosc nie ginie
                kept.append(f"{HEADERS[k][0].capitalize()} (stary CRM): {r[C[k]]}")
            return d
        rd = pd("received_d")
        opp_d = pd("opp_created")
        if rd is None and opp_d:
            # w pelnym eksporcie wiekszosc wierszy nie ma daty wplyniecia - lead
            # powstal razem z szansa
            rd = opp_d
            warn(f"{ctx}: brak daty wplyniecia - uzyto daty szansy sprzedazy")
        if rd is None:
            warn(f"{ctx}: brak daty wplyniecia i daty szansy - wiersz pominiety")
            continue
        rt = time(0)
        if r[C["received_t"]]:
            for fmt in ("%I:%M:%S %p", "%H:%M:%S", "%H:%M", "%I:%M %p"):
                try:
                    rt = datetime.strptime(r[C["received_t"]], fmt).time()
                    break
                except ValueError:
                    continue
            else:
                warn(f"{ctx}: nieczytelna godzina '{r[C['received_t']]}' - 00:00")
        received = datetime.combine(rd, rt, TZ)
        client_created = at(pd("client_created"), hour=0) or received
        if client_created.date() == received.date():
            client_created = received  # klient powstaje razem z leadem
        d_needs, d_demo = pd("needs"), pd("demo")
        d_offer, d_disc = pd("offer_sent"), pd("offer_discussed")
        d_csent, d_sign = pd("contract_sent"), pd("contract_signed")
        d_lost = pd("lost_d")
        if not opp_d and any((d_needs, d_demo, d_offer, d_disc, d_csent, d_sign)):
            # kamienie milowe bez daty szansy: szansa istniala - bierzemy
            # najwczesniejszy kamien jako date jej utworzenia
            opp_d = min(d for d in (d_needs, d_demo, d_offer, d_disc, d_csent, d_sign) if d)
            warn(f"{ctx}: brak 'Data szansy sprzedazy' - uzyto najwczesniejszej "
                 f"daty kamienia milowego")

        # --- pola leada
        src = pick(r[C["source"]], LEAD_SOURCE, warn, ctx, "źródło", kept)
        chan = pick(r[C["channel"]], CHANNEL, warn, ctx, "forma kontaktu", kept,
                    {"email": "Mail"})
        qual = pick(r[C["qualification"]], QUALIFICATION, warn, ctx, "kwalifikacja", kept)
        dq_text = r[C["disq_reason"]]
        dq = disq_reason(dq_text) if qual in ("non-MQL", "non-SQL") else None
        seller = r[C["seller"]]
        owner_id = None
        if seller:
            hits = match_employee(seller, employees)
            if len(hits) == 1:
                owner_id = hits[0]
            else:
                warn(f"{ctx}: handlowiec '{seller}' - dopasowan: {len(hits)}, "
                     f"owner pominiety")
        notes = [r[C["notes"]]] + kept
        for key, prefix in EXTRA_NOTES.items():
            if r[C[key]]:
                notes.append(prefix + r[C[key]])
        if r[C["planned_d"]]:
            notes.append(f"Data planowanego działania (stary CRM): {r[C['planned_d']]}")
        if r[C["planned"]]:
            notes.append(f"Planowane działanie (stary CRM): {r[C['planned']]}")
        if r[C["label"]]:
            notes.append(f"Etykieta szansy (stary CRM): {r[C['label']]}")
        if r[C["check_id"]]:
            notes.append(f"Spr. ID (stary CRM): {r[C['check_id']]}")

        # --- szansa
        opp = None
        if opp_d:
            opp_ts = at(opp_d, received)
            ev = [("Nowa", opp_ts)]
            for stage, d in (("Audyt", d_needs), ("Rekomendacja / demo", d_demo),
                             ("Oferta wysłana", d_offer),
                             ("Omówienie oferty", d_disc),
                             ("Umowa wysłana", d_csent),
                             ("Umowa podpisana", d_sign)):
                if d:
                    ev.append((stage, at(d, ev[-1][1])))
            state_raw = r[C["state"]].lower()
            etap = r[C["stage"]].lower()
            is_lost = bool(d_lost) or state_raw == "utracona" or etap == "utracona"
            if is_lost:
                if not d_lost:
                    warn(f"{ctx}: szansa utracona bez daty utracenia - uzyto daty "
                         f"ostatniego kamienia")
                ev.append(("Utracona", at(d_lost, ev[-1][1]) if d_lost else ev[-1][1]))
            derived = ev[-1][0]
            stage = STAGE_MAP.get(etap) if etap else None
            if etap and not stage:
                warn(f"{ctx}: nieznany Etap '{r[C['stage']]}' - uzyto {derived}")
            if stage and stage != derived:
                warn(f"{ctx}: Etap '{r[C['stage']]}' -> {stage}, ale daty wskazuja "
                     f"{derived} - uzyto Etapu")
            stage = stage or derived
            if is_lost:
                state = "lost"
            elif d_sign or stage == "Umowa podpisana" or state_raw == "zamknięta":
                state = "won"
                if not d_sign:
                    warn(f"{ctx}: wygrana bez daty podpisania umowy")
            else:
                state = "open"
            lost_text = r[C["loss_reason"]]
            opp = dict(ev=ev, stage=stage, state=state,
                       loss=loss_reason(lost_text) if state == "lost" else None,
                       loss_note=lost_text if state == "lost" else None,
                       closed=d_sign if state == "won" else (d_lost if state == "lost" else None))
        else:
            if d_lost or r[C["state"]].lower() == "utracona":
                notes.append(
                    f"Utracone w starym CRM"
                    f"{' ' + d_lost.isoformat() if d_lost else ''}: "
                    f"{r[C['loss_reason']] or dq_text or 'bez powodu'}")
        lead_notes = "\n".join(n for n in notes if n)

        # ================= SQL dla wiersza =================
        emit(f"-- ---- stary CRM #{lid}: {lead_name}")
        emit(f"IF NOT EXISTS (SELECT 1 FROM {REGISTRY} WHERE export_id = {lid}) THEN")
        emit("v_company := NULL; v_person := NULL; v_opp := NULL;")
        if company:
            emit(f"SELECT id INTO v_company FROM {SCHEMA}.companies "
                 f"WHERE lower(name) = lower({q(company)}) LIMIT 1;")
            emit("IF v_company IS NULL THEN "
                 f"INSERT INTO {SCHEMA}.companies (name, industry, created_at) "
                 f"VALUES ({q(company)}, {q(ind)}, {ts_lit(client_created)}) "
                 "RETURNING id INTO v_company; n_companies := n_companies + 1; "
                 f"ELSE UPDATE {SCHEMA}.companies SET created_at = "
                 f"LEAST(created_at, {ts_lit(client_created)}) WHERE id = v_company; END IF;")
        if email:
            emit(f"SELECT id INTO v_person FROM {SCHEMA}.persons "
                 f"WHERE lower(email) = {q(email)} LIMIT 1;")
        if core:
            emit(f"IF v_person IS NULL THEN SELECT id INTO v_person FROM {SCHEMA}.persons "
                 f"WHERE regexp_replace(coalesce(phone,''), '\\D', '', 'g') LIKE "
                 f"{q('%' + core)} LIMIT 1; END IF;")
        emit("IF v_person IS NULL THEN "
             f"INSERT INTO {SCHEMA}.persons (full_name, email, phone, industry, "
             f"created_at) VALUES ({q(person_name)}, {q(email)}, {q(phone)}, "
             f"{q(ind if not b2b else None)}, {ts_lit(client_created)}) "
             "RETURNING id INTO v_person; n_persons := n_persons + 1; "
             f"ELSE UPDATE {SCHEMA}.persons SET created_at = "
             f"LEAST(created_at, {ts_lit(client_created)}) WHERE id = v_person; END IF;")
        if company:
            emit(link(links, "person_company", "v_person", "v_company"))
        # lead
        lcols = ["lead_name", "lead_type", "lead_source", "contact_channel",
                 "qualification", "disqualify_reason", "disqualify_note",
                 "received_at", "notes", "created_at"]
        lvals = [q(lead_name), q(segment), q(src), q(chan), q(qual), q(dq),
                 q(dq_text if dq else None), ts_lit(received), q(lead_notes),
                 ts_lit(received)]
        emit(f"INSERT INTO {SCHEMA}.leads ({', '.join(ident(c) for c in lcols)}) "
             f"VALUES ({', '.join(lvals)}) RETURNING id INTO v_lead; "
             "n_leads := n_leads + 1;")
        emit(link(links, "lead_persons", "v_lead", "v_person"))
        emit(link(links, "lead_primary_person", "v_lead", "v_person"))
        if company:
            emit(link(links, "lead_company", "v_lead", "v_company"))
        if owner_id:
            emit(link(links, "lead_owner", "v_lead", str(owner_id)))
        payload = '{"legacy_id": %d}' % lid
        emit(f"INSERT INTO {SCHEMA}.activities (summary, type, triggered_by, flow, "
             f"payload, created_at) VALUES "
             f"({q('Lead zaimportowany ze starego CRM: ' + lead_name)}, 'lead_created', "
             f"'import', 'import-crm-legacy', "
             f"{q(payload)}, {ts_lit(received)}) RETURNING id INTO v_act;")
        emit(link(links, "lead_activities", "v_lead", "v_act"))
        if opp:
            ocols = ["name", "segment", "stage", "state", "loss_reason", "loss_note",
                     "deal_value", "offer_sent_at", "contract_sent_at", "closed_at",
                     "stage_changed_at", "notes", "legacy_id", "created_at"]
            ovals = [q(lead_name), q(segment), q(opp["stage"]), q(opp["state"]),
                     q(opp["loss"]), q(opp["loss_note"]),
                     money(r[C["value"]]) or "NULL", date_lit(d_offer),
                     date_lit(d_csent), date_lit(opp["closed"]),
                     ts_lit(opp["ev"][-1][1]), q(lead_notes), str(lid),
                     ts_lit(opp["ev"][0][1])]
            emit(f"INSERT INTO {SCHEMA}.sale_opportunities "
                 f"({', '.join(ident(c) for c in ocols)}) VALUES "
                 f"({', '.join(ovals)}) RETURNING id INTO v_opp; "
                 "n_opps := n_opps + 1;")
            emit(link(links, "opp_person", "v_opp", "v_person"))
            emit(link(links, "opp_source_lead", "v_opp", "v_lead"))
            if company:
                emit(link(links, "opp_company", "v_opp", "v_company"))
            if owner_id:
                emit(link(links, "opp_owner", "v_opp", str(owner_id)))
            prev = None
            for stage, ts in opp["ev"]:
                title = f"{prev} → {stage}" if prev else f"→ {stage}"
                emit(f"INSERT INTO {SCHEMA}.sale_opportunity_stage_history "
                     f"(title, from_stage, to_stage, changed_at, changed_by, "
                     f"created_at) VALUES ({q(title)}, {q(prev)}, "
                     f"{q(stage)}, {ts_lit(ts)}, 'import', {ts_lit(ts)}) "
                     "RETURNING id INTO v_hist;")
                emit(link(links, "history_opp", "v_hist", "v_opp"))
                emit("n_history := n_history + 1;")
                prev = stage
        emit(f"INSERT INTO {REGISTRY} (export_id, lead_id, opportunity_id, source) "
             f"VALUES ({lid}, v_lead, v_opp, 'import');")
        emit("ELSE n_skipped := n_skipped + 1; END IF;")
    return "\n".join(out)



def group_warnings(warnings, examples=3):
    """Ostrzezenia z tysiecy wierszy -> "N× tresc (np. #1, #2, #3)"; raport
    miesci sie w polu tekstowym NocoDB."""
    groups = {}
    for w in warnings:
        m = re.match(r"(#\d+)(?: [a-z_]+)?: (.*)", w)
        key, ex = (re.sub(r"[\d/.\-]{4,}|'[^']*'", "…", m[2]), m[1]) if m else (w, "")
        g = groups.setdefault(key, [0, []])
        g[0] += 1
        if ex and len(g[1]) < examples:
            g[1].append(ex)
    return [f"{n}× {k}" + (f" (np. {', '.join(ex)})" if ex else "")
            for k, (n, ex) in sorted(groups.items(), key=lambda kv: -kv[1][0])]


def run_import(db, data, schema_map, apply=False, export_date=date(2026, 10, 30),
               sql_out=None):
    """Importuje CSV (bytes). Zwraca dict z licznikami i ostrzezeniami."""
    warnings = []
    warn = warnings.append
    text = decode(data)
    rows, table_notes = read_table(text)
    links = discover(db, schema_map)
    employees = [(int(i), n) for i, n in
                 db.run(f"SELECT id, full_name FROM {SCHEMA}.employees", tuples=True)]
    body = build(rows, links, employees, export_date, warn)
    # Paczki po BATCH wierszy, kazda we wlasnym bloku DO (w jednej transakcji):
    # PL/pgSQL trzyma plany WSZYSTKICH instrukcji bloku do jego konca - jeden blok
    # na caly plik przekroczyl 512 MB kontenera Postgresa (OOM, restart bazy).
    blocks = [b for b in re.split(r"(?m)^(?=-- ---- stary CRM #)", body) if b.strip()]
    parts = ["BEGIN;"]
    for i in range(0, len(blocks), BATCH):
        parts.append(
            "DO $import$\nDECLARE\n"
            "  v_company bigint; v_person bigint; v_lead bigint; v_opp bigint;\n"
            "  v_act bigint; v_hist bigint;\n"
            "  n_companies int := 0; n_persons int := 0; n_leads int := 0;\n"
            "  n_opps int := 0; n_history int := 0; n_skipped int := 0;\nBEGIN\n"
            + "".join(blocks[i:i + BATCH]) +
            "\nRAISE NOTICE 'companies=%, persons=%, leads=%, opportunities=%, "
            "history=%, skipped=%', n_companies, n_persons, "
            "n_leads, n_opps, n_history, n_skipped;\n"
            "END $import$;")
    parts.append(f"{'COMMIT' if apply else 'ROLLBACK'};\n")
    sql = "\n".join(parts)
    if apply:
        # sekwencja numerow dla rekordow z nowego CRM startuje za najwiekszym ID
        # z importu (setval nie jest transakcyjny - dlatego dopiero po COMMIT)
        sql += (f"SELECT setval('legacy.export_id_seq', greatest(m.v, s.v)) FROM "
                f"(SELECT coalesce(max(export_id), 0) v FROM {REGISTRY}) m, "
                f"(SELECT CASE WHEN is_called THEN last_value ELSE 0 END v "
                f"FROM legacy.export_id_seq) s WHERE greatest(m.v, s.v) > 0;\n")
    if sql_out:
        with open(sql_out, "w", encoding="utf-8") as f:
            f.write(sql)
    res = db.run(sql)
    found = re.findall(r"companies=(\d+), persons=(\d+), leads=(\d+), "
                       r"opportunities=(\d+), history=(\d+), skipped=(\d+)", res)
    if not found and blocks:
        raise LegacyError(f"Brak podsumowania z bazy: {res[-300:]}")
    keys = ("companies", "persons", "leads", "opportunities", "history", "skipped")
    counts = {k: sum(int(f[i]) for f in found) for i, k in enumerate(keys)}
    return dict(
        ok=True, applied=apply, rows=len(rows),
        counts=counts,
        warnings=table_notes + group_warnings(warnings),
        warnings_total=len(warnings), links=list(links),
        sha256=hashlib.sha256(data).hexdigest())
