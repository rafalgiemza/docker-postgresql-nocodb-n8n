#!/usr/bin/env python3
r"""Seeduje dane testowe CRM v4 przez NocoDB REST API, ETAPAMI zgodnymi z
budową schematu (docs/archive/fable/nocodb_crm_migration_v4.md, sekcja „Dane
testowe (seedy)"). Wzorowany na scripts/demo-seed.py: `rec()` / `lnk()`, id
pól relacji znajdowane po tytule, `--dry-run`, daty względne od dnia
uruchomienia (żeby widoki „Utknięte" i „Moje zadania" zawsze miały co pokazać).

Zestaw danych rośnie z etapami:
  1  pracownicy, urlop z zastępstwem, firmy Acme i Beta, osoby, leady, szanse
     (B2C Anna, B2B Acme, Beta w audycie, utknięta, przegrana), historia
     etapów, zadania (todo / scheduled / done)
  2  spotkania: discovery i demo, spotkanie księgowej bez szansy, spotkanie
     bez typu (do widoku kontrolnego)
  3  audyty, oceny, to_be_audited / audited / participants, audit_scope,
     zadania audit_prep
  4  rekomendacje, oferty (Anna draft, Acme v1 odrzucona i v2 przyjęta z
     approved_total). Katalogi (cennik, pakiety, szablony) wgrywają osobne
     skrypty importu; seed podpina pierwsze znalezione wiersze, a brak
     katalogu tylko ostrzega.

Etapy są POWTARZALNE: każdy ma rekord kontrolny (osoba / spotkanie /
ocena / oferta o znanym kluczu) i jest pomijany, jeśli już był seedowany.
Rekordy wcześniejszych etapów są odnajdywane po stabilnych kluczach (e-mail
osoby, nazwa szansy, `external_id` spotkania), zmiana tych kluczy w etapie 1
wymaga zmiany w kolejnych. Skrypt nie dedupe'uje poza tym i nie dotyka tabel
spoza CRM v4.

Wymaga: NC_API_TOKEN, NC_CRM_BASE_ID (opcjonalnie NC_LOCAL_URL) i tabel
utworzonych przez `make init-schema STAGE=N` dla żądanych etapów.

Usage:
  make seed-test-data STAGE=2
  # albo bezpośrednio:
  set -a; source .env; set +a
  python3 scripts/seed-test-data.py --stage 4 --dry-run
  python3 scripts/seed-test-data.py --stage 2
"""
import argparse
import importlib.util
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "init_schema", Path(__file__).parent / "init-schema.py")
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)
api = core.api

COUNTS = {"created": 0, "linked": 0, "errors": 0}
DRY = False
TABLE_IDS = {}
LINK_FIELDS = {}   # {tabela: {tytuł_pola_lower: field_id}}
K = {}             # klucze rekordów (id) widoczne dla kolejnych etapów
_fake = {"n": 0}

# Stałe klucze rekordów kontrolnych / wyszukiwania
EMAIL = {
    "przemek": "przemek@coaction.example", "dorota": "dorota@coaction.example",
    "aleksandra": "aleksandra@coaction.example", "paulina": "paulina@coaction.example",
    "anna": "anna.nowak@example.com", "marek": "marek@acme.example",
    "joanna": "joanna.lis@acme.example", "tomasz": "tomasz.brzezinski@acme.example",
    "ewa": "ewa@acme.example", "piotr": "piotr@acme.example",
    "karol": "karol@acme.example", "beata": "beata.ksiegowa@acme.example",
    "oliwia": "oliwia.nowicka@beta.example", "adam": "adam@beta.example",
    "ewelina": "ewelina@beta.example", "jan": "jan.kowalski@example.com",
    "katarzyna": "katarzyna.zielinska@example.com", "lis": "piotr.lis@example.com",
}
OPP = {
    "anna": "Anna Nowak – kurs 1:1", "acme": "Acme – audyty i kurs",
    "beta": "Beta – audyty", "kasia": "Katarzyna Zielińska – kurs",
    "lis": "Piotr Lis – kurs",
}


def d(offset_days):
    return (date.today() + timedelta(days=offset_days)).isoformat()


def dt(offset_days, hour=10):
    return (datetime.now() + timedelta(days=offset_days)).replace(
        hour=hour, minute=0, second=0, microsecond=0).isoformat()


def rec(table, **fields):
    """Tworzy rekord, zwraca Id (w dry-run: numer zastępczy)."""
    fields = {k: v for k, v in fields.items() if v is not None}
    label = next((fields[k] for k in ("full_name", "name", "title", "lead_name")
                  if k in fields), "?")
    if DRY:
        _fake["n"] += 1
        print(f"  + [dry-run] {table}: {label}")
        return _fake["n"]
    try:
        res = api("POST", f"/api/v2/tables/{TABLE_IDS[table]}/records", json=fields)
    except SystemExit as e:
        COUNTS["errors"] += 1
        print(f"  ! {table}: {label} -> {e}")
        return None
    rid = res.get("Id") or (res[0].get("Id") if isinstance(res, list) else None)
    COUNTS["created"] += 1
    print(f"  + {table}: {label} (Id={rid})")
    return rid


def lnk(table, field, owner_id, target_ids):
    """Linkuje `table`.`field` rekordu owner_id -> target_ids (pole właściciela
    z RELATIONS; pole zwrotne uzupełnia NocoDB)."""
    ids = [i for i in (target_ids if isinstance(target_ids, list) else [target_ids])
           if i is not None]
    if owner_id is None or not ids:
        return
    if DRY:
        print(f"    ~ [dry-run] {table}#{owner_id}.{field} -> {ids}")
        return
    fid = LINK_FIELDS.get(table, {}).get(field.lower())
    if not fid:
        COUNTS["errors"] += 1
        print(f"    ! link {table}.{field}: pole nie znalezione "
              f"(dostępne: {list(LINK_FIELDS.get(table, {}))})")
        return
    try:
        api("POST", f"/api/v2/tables/{TABLE_IDS[table]}/links/{fid}/records/{owner_id}",
            json=[{"Id": i} for i in ids])
    except SystemExit as e:
        COUNTS["errors"] += 1
        print(f"    ! link {table}#{owner_id}.{field}: {e}")
        return
    COUNTS["linked"] += 1
    print(f"    ~ {table}#{owner_id}.{field} -> {ids}")


def find_id(table, field, value):
    """Id pierwszego rekordu z field = value albo None (w dry-run: None)."""
    if DRY or table not in TABLE_IDS:
        return None
    res = api("GET", f"/api/v2/tables/{TABLE_IDS[table]}/records",
              params={"where": f"({field},eq,{value})", "limit": 1})
    rows = res.get("list", [])
    return rows[0]["Id"] if rows else None


def first_id(table):
    if DRY or table not in TABLE_IDS:
        return None
    res = api("GET", f"/api/v2/tables/{TABLE_IDS[table]}/records", params={"limit": 1})
    rows = res.get("list", [])
    return rows[0]["Id"] if rows else None


def load_ids():
    """Id istniejących tabel CRM v4 i id ich pól relacji (po tytule)."""
    tables = core.existing_tables()
    for title in core.BUILD_STAGE_OF:
        tid = tables.get(title.lower())
        if not tid:
            continue
        TABLE_IDS[title] = tid
        LINK_FIELDS[title] = {
            c["title"].strip().lower(): c["id"]
            for c in api("GET", f"/api/v2/meta/tables/{tid}").get("columns", [])
            if c.get("uidt") in ("Links", "LinkToAnotherRecord")}


def need_tables(*titles):
    missing = [t for t in titles if t not in TABLE_IDS] if not DRY else []
    if missing:
        sys.exit(f"Brak tabel {missing}: najpierw `make init-schema STAGE=N`.")


# ------------------------------------------------------------ helpery domenowe
def history(opp_id, steps):
    """steps: [(etap, ile_dni_temu)], w kolejności. Pierwszy wiersz bez from_stage."""
    prev = None
    for stage, days_ago in steps:
        title = f"{prev} → {stage}" if prev else f"Utworzono: {stage}"
        rid = rec("sale_opportunity_stage_history", title=title, from_stage=prev,
                  to_stage=stage, changed_at=dt(-days_ago), changed_by="seed")
        lnk("sale_opportunities", "history", opp_id, rid)
        prev = stage


def task(title, task_type, status, assignee, opp=None, person=None, lead=None,
         meeting=None, assessment=None, due=None, scheduled=None):
    rid = rec("tasks", title=title, task_type=task_type, status=status,
              due_date=d(due) if due is not None else None,
              scheduled_for=d(scheduled) if scheduled is not None else None,
              created_by_flow="seed")
    lnk("employees", "tasks", assignee, rid)
    lnk("persons", "tasks", person, rid)
    lnk("sale_opportunities", "tasks", opp, rid)
    lnk("leads", "tasks", lead, rid)
    if "meetings" in TABLE_IDS:
        lnk("meetings", "tasks", meeting, rid)
    if "assessments" in TABLE_IDS:
        lnk("assessments", "tasks", assessment, rid)
    return rid


def meeting(opp, title, mtype, ext, days, hour, attendees, owner, status="done"):
    mid = rec("meetings", title=title, meeting_type=mtype, external_id=ext,
              starts_at=dt(days, hour), status=status)
    lnk("employees", "meetings", owner, mid)
    lnk("sale_opportunities", "meetings", opp, mid)
    lnk("meetings", "attendees", mid, attendees)
    return mid


def lookup_stage1():
    """Odnajduje rekordy etapu 1 po stabilnych kluczach (dla etapów 2-4)."""
    if DRY:
        return   # w dry-run klucze zostały ustawione przez seed_stage1() w tym samym przebiegu
    for key in ("przemek", "dorota", "aleksandra", "paulina"):
        K[key] = find_id("employees", "email", EMAIL[key])
    for key in ("anna", "marek", "joanna", "tomasz", "ewa", "piotr", "karol", "beata",
                "oliwia", "adam", "ewelina", "jan", "katarzyna"):
        K[key] = find_id("persons", "email", EMAIL[key])
    for key, name in OPP.items():
        K["opp_" + key] = find_id("sale_opportunities", "name", name)


# ------------------------------------------------------------------ etap 1
def seed_stage1():
    need_tables("employees", "absences", "companies", "persons", "leads",
                "sale_opportunities", "sale_opportunity_stage_history", "tasks")
    if find_id("employees", "email", EMAIL["przemek"]):
        print("\n=== Etap 1: już seedowany (znaleziono pracownika), pomijam ===")
        return
    print("\n=== Etap 1: zespół, firmy, osoby, leady, szanse, zadania ===")
    for key, name, role in (("przemek", "Przemek", "handlowiec"),
                            ("dorota", "Dorota", "metodyczka"),
                            ("aleksandra", "Aleksandra", "metodyczka"),
                            ("paulina", "Paulina", "finanse")):
        K[key] = rec("employees", full_name=name, email=EMAIL[key], role=role,
                     is_active=True)
    absence = rec("absences", title="Przemek – urlop", absence_type="urlop",
                  start_date=d(3), end_date=d(10))
    lnk("employees", "absences", K["przemek"], absence)
    lnk("absences", "substitutes", absence, K["dorota"])

    acme = rec("companies", name="Acme Sp. z o.o.", nip="5252000001", industry="IT",
               size="10-50")
    beta = rec("companies", name="Beta Sp. z o.o.", nip="5252000002", industry="Finance",
               size="<10")

    def person(key, name, position=None, **kw):
        K[key] = rec("persons", full_name=name, email=EMAIL[key], position=position, **kw)
        return K[key]

    person("anna", "Anna Nowak", "Product Manager", industry="IT")
    person("marek", "Marek Zieliński", "CEO")
    person("joanna", "Joanna Lis", "HR Director")
    person("tomasz", "Tomasz Brzeziński", "CFO")
    person("ewa", "Ewa Kowalska", "Project Manager")
    person("piotr", "Piotr Wiśniewski", "Sales Manager")
    person("karol", "Karol Mazur", "Developer")
    person("beata", "Beata Księgowa", "Główna księgowa", sales_mode="Tylko spotkania")
    person("oliwia", "Oliwia Nowicka", "HR Manager")
    person("adam", "Adam Lewandowski", "Analyst")
    person("ewelina", "Ewelina Kaczmarek", "Controller")
    person("jan", "Jan Kowalski")
    person("katarzyna", "Katarzyna Zielińska", "Architekt")
    person("lis", "Piotr Lis")
    lnk("companies", "persons", acme, [K[k] for k in
        ("marek", "joanna", "tomasz", "ewa", "piotr", "karol", "beata")])
    lnk("companies", "persons", beta, [K[k] for k in ("oliwia", "adam", "ewelina")])
    lnk("employees", "assigned_persons", K["dorota"],
        [K[k] for k in ("ewa", "piotr", "karol", "oliwia", "adam", "ewelina")])
    lnk("employees", "assigned_persons", K["aleksandra"], K["anna"])

    # --- leady
    def lead(name, ltype, source, qual, persons, primary, owner, company=None,
             days=-30, converted=False):
        lid = rec("leads", lead_name=name, lead_type=ltype, lead_source=source,
                  contact_channel="Formularz", qualification=qual,
                  received_at=dt(days), convert_status="done" if converted else None)
        lnk("leads", "persons", lid, persons)
        lnk("persons", "primary_in_leads", primary, lid)
        lnk("employees", "leads", owner, lid)
        if company:
            lnk("companies", "leads", company, lid)
        return lid

    l_anna = lead("Anna Nowak – formularz", "B2C", "Google", "SQL", [K["anna"]],
                  K["anna"], K["przemek"], converted=True)
    l_acme = lead("Acme – audyty dla 3 pracowników", "B2B", "Recommendation", "SQL",
                  [K["marek"], K["joanna"], K["tomasz"]], K["marek"], K["przemek"],
                  company=acme, converted=True)
    l_beta = lead("Beta – audyty", "B2B", "LinkedIn", "SQL", [K["oliwia"]], K["oliwia"],
                  K["przemek"], company=beta, days=-10, converted=True)
    l_jan = lead("Jan Kowalski – formularz", "B2C", "Google", "unqualified", [K["jan"]],
                 K["jan"], K["przemek"], days=-1)

    # --- szanse
    def opp(key, name, segment, stage, state, value, owner, buyer, lead_id=None,
            company=None, label="Nowy klient", **kw):
        oid = rec("sale_opportunities", name=name, segment=segment, stage=stage,
                  state=state, deal_value=value, label=label, **kw)
        K["opp_" + key] = oid
        lnk("persons", "bought_opportunities", buyer, oid)
        lnk("employees", "opportunities", owner, oid)
        if lead_id:
            lnk("leads", "opportunities", lead_id, oid)
        if company:
            lnk("companies", "opportunities", company, oid)
        return oid

    o_anna = opp("anna", OPP["anna"], "B2C", "Rekomendacja / demo", "open", 4800,
                 K["przemek"], K["anna"], l_anna, stage_changed_at=dt(-6),
                 training_goals="Swobodne rozmowy ze zleceniodawcami z zagranicy.")
    history(o_anna, [("Nowa", 28), ("Discovery umówione", 26), ("Discovery odbyte", 24),
                     ("Audyt", 17), ("Rekomendacja / demo", 6)])

    o_acme = opp("acme", OPP["acme"], "B2B", "Umowa podpisana", "won", 9600,
                 K["przemek"], K["marek"], l_acme, acme, stage_changed_at=dt(-1),
                 offer_sent_at=d(-4), contract_sent_at=d(-3), closed_at=d(-1),
                 service_end_date=d(180),
                 audit_scope="Prezentacje handlowe i spotkania z klientami z UK.")
    history(o_acme, [("Nowa", 28), ("Discovery umówione", 26), ("Discovery odbyte", 24),
                     ("Audyt", 18), ("Rekomendacja / demo", 9), ("Oferta wysłana", 7),
                     ("Umowa wysłana", 3), ("Umowa podpisana", 1)])

    o_beta = opp("beta", OPP["beta"], "B2B", "Audyt", "open", 3000, K["przemek"],
                 K["oliwia"], l_beta, beta, stage_changed_at=dt(-3),
                 audit_scope="Komunikacja z zagranicznymi bankami.")
    history(o_beta, [("Nowa", 10), ("Discovery umówione", 9), ("Discovery odbyte", 7),
                     ("Audyt", 3)])

    o_kasia = opp("kasia", OPP["kasia"], "B2C", "Oferta wysłana", "open", 5200,
                  K["przemek"], K["katarzyna"], label="Odnowienie",
                  stage_changed_at=dt(-20), offer_sent_at=d(-20))
    history(o_kasia, [("Nowa", 40), ("Audyt", 30), ("Oferta wysłana", 20)])

    o_lis = opp("lis", OPP["lis"], "B2C", "Utracona", "lost", 3600, K["przemek"],
                K["lis"], stage_changed_at=dt(-10), closed_at=d(-10),
                loss_reason="cena", loss_note="Wybrał tańszą ofertę konkurencji.")
    history(o_lis, [("Nowa", 25), ("Oferta wysłana", 15), ("Utracona", 10)])

    # --- zadania (todo / scheduled / done)
    task("Zakwalifikuj leada: Jan Kowalski", "qualify_lead", "todo", K["przemek"],
         person=K["jan"], lead=l_jan, due=0)
    task("Umów discovery call z Anną", "other", "done", K["przemek"],
         person=K["anna"], opp=o_anna, due=-28)
    task("Odezwać się do Katarzyny Zielińskiej", "other", "scheduled", K["przemek"],
         person=K["katarzyna"], opp=o_kasia, scheduled=1)
    # termin w czasie urlopu Przemka -> zadanie przejmuje zastępczyni
    task("Wrócić do Marka w sprawie Karola (zastępstwo za Przemka)", "other",
         "scheduled", K["dorota"], person=K["marek"], opp=o_acme, scheduled=5)
    task("Wystawić fakturę: Acme", "invoice", "todo", K["paulina"], person=K["marek"],
         opp=o_acme, due=3)


# ------------------------------------------------------------------ etap 2
def seed_stage2():
    need_tables("meetings")
    if find_id("meetings", "external_id", "seed-anna-discovery"):
        print("\n=== Etap 2: już seedowany, pomijam ===")
        return
    lookup_stage1()
    if not DRY and not K.get("opp_anna"):
        sys.exit("Brak danych etapu 1: najpierw `seed-test-data --stage 1`.")
    print("\n=== Etap 2: spotkania ===")
    meeting(K["opp_anna"], "Discovery call: Anna Nowak", "discovery", "seed-anna-discovery",
            -24, 10, K["anna"], K["przemek"])
    meeting(K["opp_anna"], "Prezentacja propozycji: Anna Nowak", "demo", "seed-anna-demo",
            -6, 11, K["anna"], K["przemek"])
    meeting(K["opp_acme"], "Discovery call: Acme (Marek)", "discovery",
            "seed-acme-discovery", -24, 10, K["marek"], K["przemek"])
    meeting(K["opp_acme"], "Prezentacja propozycji: Acme (Marek)", "demo",
            "seed-acme-demo", -9, 15, K["marek"], K["przemek"])
    meeting(K["opp_beta"], "Discovery call: Beta (Oliwia)", "discovery",
            "seed-beta-discovery", -7, 12, K["oliwia"], K["przemek"])
    # księgowa (sales_mode = Tylko spotkania): spotkanie bez szansy i bez leada
    meeting(None, "Faktury i rozliczenia: Acme (księgowa)", "inne", "seed-beata-faktury",
            -5, 13, K["beata"], K["paulina"])
    # spotkanie bez typu -> widok kontrolny „Spotkania bez typu"
    mid = rec("meetings", title="Rezerwacja cal.com (typ do ustawienia)",
              external_id="seed-bez-typu", starts_at=dt(2, 14), status="scheduled")
    lnk("employees", "meetings", K["przemek"], mid)
    lnk("meetings", "attendees", mid, K["jan"])


# ------------------------------------------------------------------ etap 3
def seed_stage3():
    need_tables("assessments", "meetings")
    if find_id("assessments", "title", "Ewa Kowalska – audyt"):
        print("\n=== Etap 3: już seedowany, pomijam ===")
        return
    lookup_stage1()
    if not DRY and not K.get("opp_acme"):
        sys.exit("Brak danych etapu 1: najpierw `seed-test-data --stage 1`.")
    print("\n=== Etap 3: audyty, oceny, listy osób ===")

    def audit(opp, who, name, days, owner, cefr, summary, status="ai_accepted"):
        mid = meeting(opp, f"Audyt: {name}", "audit", f"seed-audit-{who}", -days, 9,
                      K[who], owner)
        aid = rec("assessments", title=f"{name} – audyt", assessed_at=d(-days),
                  cefr_overall=cefr, needs_summary=summary, ai_status=status,
                  self_assessment="Czuję się pewnie w mowie, słabiej w negocjacjach.",
                  manager_needs="Poprawa płynności w spotkaniach z klientem.")
        lnk("persons", "assessments", K[who], aid)
        lnk("meetings", "assessments", mid, aid)
        return mid, aid

    # B2C Anna
    audit(K["opp_anna"], "anna", "Anna Nowak", 17, K["aleksandra"], "B1",
          "Potrzebuje swobody w rozmowach ze zleceniodawcami z zagranicy.")
    lnk("sale_opportunities", "audited", K["opp_anna"], K["anna"])
    task("Przygotowanie audytu: Anna Nowak", "audit_prep", "done", K["aleksandra"],
         opp=K["opp_anna"], person=K["anna"], due=-20,
         meeting=find_id("meetings", "external_id", "seed-anna-discovery"))

    # B2B Acme: trzy audyty, participants = Ewa i Piotr
    for who, name, days, cefr, summary in (
            ("ewa", "Ewa Kowalska", 18, "B2", "Prowadzi spotkania z klientami z UK."),
            ("piotr", "Piotr Wiśniewski", 17, "B1", "Prezentacje handlowe po angielsku."),
            ("karol", "Karol Mazur", 16, "B1", "Głównie komunikacja pisemna.")):
        audit(K["opp_acme"], who, name, days, K["dorota"], cefr, summary)
        task(f"Przygotowanie audytu: {name} (Acme)", "audit_prep", "done", K["dorota"],
             opp=K["opp_acme"], person=K[who], due=-days - 2,
             meeting=find_id("meetings", "external_id", "seed-acme-discovery"))
    lnk("sale_opportunities", "audited", K["opp_acme"],
        [K["ewa"], K["piotr"], K["karol"]])
    lnk("sale_opportunities", "participants", K["opp_acme"], [K["ewa"], K["piotr"]])

    # B2B Beta: dwie osoby czekają na audyt, dwa zadania do zrobienia
    lnk("sale_opportunities", "to_be_audited", K["opp_beta"], [K["adam"], K["ewelina"]])
    for who, name in (("adam", "Adam Lewandowski"), ("ewelina", "Ewelina Kaczmarek")):
        task(f"Przygotowanie audytu: {name} (Beta)", "audit_prep", "todo", K["dorota"],
             opp=K["opp_beta"], person=K[who], due=2,
             meeting=find_id("meetings", "external_id", "seed-beta-discovery"))
    # jedna ocena jako szkic AI do zatwierdzenia (widok „Szkice AI")
    mid = meeting(K["opp_beta"], "Audyt: Oliwia Nowicka", "audit", "seed-audit-oliwia",
                  -1, 9, K["oliwia"], K["dorota"])
    aid = rec("assessments", title="Oliwia Nowicka – audyt", assessed_at=d(-1),
              cefr_overall="B2", needs_summary="Szkic do weryfikacji.",
              ai_status="ai_draft_ready")
    lnk("persons", "assessments", K["oliwia"], aid)
    lnk("meetings", "assessments", mid, aid)
    lnk("sale_opportunities", "audited", K["opp_beta"], K["oliwia"])


# ------------------------------------------------------------------ etap 4
def seed_stage4():
    need_tables("recommendations", "offers")
    if find_id("offers", "title", "Oferta – Acme v1"):
        print("\n=== Etap 4: już seedowany, pomijam ===")
        return
    lookup_stage1()
    if not DRY and not K.get("opp_acme"):
        sys.exit("Brak danych etapu 1: najpierw `seed-test-data --stage 1`.")
    print("\n=== Etap 4: rekomendacje i oferty ===")
    template = first_id("document_templates")
    pricing = first_id("pricing")
    if not DRY and not template:
        print("  ! document_templates puste: oferty bez szablonu (najpierw wgraj szablony)")
    if not DRY and not pricing:
        print("  ! pricing puste: oferty bez wiersza cennika (najpierw import-pricing)")

    def recommendation(who, name, rtype="business_english"):
        rid = rec("recommendations", title=f"Rekomendacja: {name}", type=rtype,
                  headline="Business English dopasowany do roli",
                  rationale="Na podstawie audytu: priorytet to płynność i słownictwo "
                            "negocjacyjne.", priority="wysoki", ai_status="ai_accepted")
        lnk("persons", "recommendations", K[who], rid)
        return rid

    def offer(opp, title, version, status, recs, total=None, sent=None):
        oid = rec("offers", title=title, version=version, status=status, hours=40,
                  product_type="standard", approved_total=total,
                  sent_at=d(sent) if sent is not None else None, valid_until=d(14))
        lnk("sale_opportunities", "offers", opp, oid)
        lnk("offers", "recommendations", oid, recs)
        if template:
            lnk("document_templates", "offers", template, oid)
        if pricing:
            lnk("offers", "pricing", oid, pricing)
        return oid

    # Anna: oferta po demo, jeszcze szkic
    r_anna = recommendation("anna", "Anna Nowak")
    offer(K["opp_anna"], "Oferta – Anna Nowak", 1, "draft", [r_anna])
    task("Przygotuj ofertę: Anna Nowak", "prepare_offer", "todo", K["przemek"],
         opp=K["opp_anna"], person=K["anna"], due=1)

    # Acme: v1 dla trzech osób (odrzucona), v2 dla dwóch (przyjęta); każda wersja
    # ma WŁASNE wiersze rekomendacji (relacja has-many, decyzja D4)
    r1 = [recommendation(k, n) for k, n in (("ewa", "Ewa Kowalska"),
                                            ("piotr", "Piotr Wiśniewski"),
                                            ("karol", "Karol Mazur"))]
    offer(K["opp_acme"], "Oferta – Acme v1", 1, "rejected", r1, total=14400, sent=-7)
    r2 = [recommendation(k, n) for k, n in (("ewa", "Ewa Kowalska"),
                                            ("piotr", "Piotr Wiśniewski"))]
    offer(K["opp_acme"], "Oferta – Acme v2", 2, "accepted", r2, total=9600, sent=-4)


STAGES = {1: seed_stage1, 2: seed_stage2, 3: seed_stage3, 4: seed_stage4}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=int, choices=range(1, 5), metavar="N", default=4,
                    help="seeduj etapy 1..N (etap już seedowany jest pomijany); "
                         "domyślnie 4")
    ap.add_argument("--dry-run", action="store_true", help="pokaż plan, nie wywołuj API")
    args = ap.parse_args()
    DRY = args.dry_run

    print(f"NocoDB: {core.URL}, base: {core.BASE_ID}{' [DRY RUN]' if DRY else ''}, "
          f"etapy 1..{args.stage}")
    if not DRY:
        load_ids()
    else:
        TABLE_IDS.update({t: f"<{t}>" for t in core.BUILD_STAGE_OF})
    for n in range(1, args.stage + 1):
        STAGES[n]()
    print(f"\nGotowe: {COUNTS['created']} rekordów, {COUNTS['linked']} linków, "
          f"{COUNTS['errors']} błędów.")
    if COUNTS["errors"]:
        print("Są błędy: sprawdź wyżej linie zaczynające się od '!'.")
