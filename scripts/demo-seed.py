#!/usr/bin/env python3
r"""Wypełnia tabele `demo_*` (utworzone przez `scripts/demo-schema-init.py`)
dwoma przykładami do pokazu koncepcji schematu v4
(docs/crm-schema-v4-proposal.md, sekcja 10):

  B2C - Anna Nowak, osoba prywatna. Szansa jest OTWARTA na etapie `Demo`:
        po formularzu, discovery, audycie i demo, przed ofertą i umową.
        Anna jest attendee trzech spotkań i ma ocenę z audytu, ale NIE jest
        jeszcze participantem (ten link powstaje dopiero przy podpisaniu).
  B2B - Acme Sp. z o.o. Marek (szef, płaci, był tylko na discovery i demo)
        kupuje szkolenie dla 2 z 3 audytowanych pracowników. Szansa jest
        WYGRANA (`Umowa podpisana`): participants = Ewa i Piotr, Karol ma
        audyt i ocenę, ale nie jest participantem.

Oba przykłady na kanbanie stoją na różnych etapach, a participants jest
puste u Anny i wypełnione u Acme - to jest kontrast, który ma być widać.
Chcesz Annę też na `Umowa podpisana`? Zmień ANNA_STAGE niżej (i dopisz
participants - patrz seed_b2c()).

Nie dotyka żadnych tabel poza `demo_*`. Odmawia działania, jeśli
`demo_persons` ma już wiersze (nie dedupe'uje - żeby nie dokładać duplikatów,
usuń wiersze demo ręcznie w UI i uruchom ponownie).

Wymaga tego samego co `make demo-schema-init` (NC_API_TOKEN, NC_CRM_BASE_ID,
opcjonalnie NC_LOCAL_URL) oraz istniejących tabel `demo_*` z relacjami v3.
Pola User (`demo_tasks.assignee`) zostawia puste.

NIEZWERYFIKOWANE NA ŻYWO: wzorzec tworzenia rekordów i linków jest skopiowany
z scripts/seed-extra.py, który działa; nowe jest tylko użycie go na tabelach
demo_*. Przy błędzie pojedynczego rekordu/linku skrypt wypisuje go i idzie
dalej, a na końcu podaje liczbę błędów.

Usage:
  make demo-seed
  # albo bezpośrednio:
  set -a; source .env; set +a
  python3 scripts/demo-seed.py --dry-run
  python3 scripts/demo-seed.py
"""
import argparse
import importlib.util
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "demo_schema_init", Path(__file__).parent / "demo-schema-init.py")
demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(demo)
core = demo.core
api = core.api

# Etap szansy Anny (otwarta). Wartość musi być jedną z demo.STAGES.
ANNA_STAGE = "Demo"

COUNTS = {"created": 0, "linked": 0}
DRY = False
TABLE_IDS = {}
LINK_FIELDS = {}   # {tabela: {tytuł_pola_lower: field_id}}
_fake = {"n": 0}


def d(offset_days):
    return (date.today() + timedelta(days=offset_days)).isoformat()


def dt(offset_days, hour):
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
    res = api("POST", f"/api/v2/tables/{TABLE_IDS[table]}/records", json=fields)
    rid = res.get("Id") or (res[0].get("Id") if isinstance(res, list) else None)
    COUNTS["created"] += 1
    print(f"  + {table}: {label} (Id={rid})")
    return rid


def lnk(table, field, owner_id, target_ids):
    """Linkuje `table`.`field` rekordu owner_id -> target_ids (pole właściciela
    z demo.REL_SPEC; pole zwrotne uzupełnia NocoDB)."""
    ids = [i for i in (target_ids if isinstance(target_ids, list) else [target_ids])
           if i is not None]
    if not ids:
        return
    if DRY:
        print(f"    ~ [dry-run] {table}#{owner_id}.{field} -> {ids}")
        return
    fid = LINK_FIELDS.get(table, {}).get(field.lower())
    if not fid:
        print(f"    ! link {table}.{field}: pole nie znalezione "
              f"(dostępne: {list(LINK_FIELDS.get(table, {}))})")
        return
    api("POST", f"/api/v2/tables/{TABLE_IDS[table]}/links/{fid}/records/{owner_id}",
        json=[{"Id": i} for i in ids])
    COUNTS["linked"] += 1
    print(f"    ~ {table}#{owner_id}.{field} -> {ids}")


def history(opp_id, steps):
    """steps: [(etap, ile_dni_temu)], w kolejności. Pierwszy wiersz bez from_stage."""
    prev = None
    for stage, days_ago in steps:
        title = f"{prev} → {stage}" if prev else f"Utworzono: {stage}"
        rid = rec("demo_stage_history", title=title, from_stage=prev,
                  to_stage=stage, changed_at=d(-days_ago))
        lnk("demo_sale_opportunities", "history", opp_id, rid)
        prev = stage


def task(title, status, due_offset, person_id, opp_id):
    rid = rec("demo_tasks", title=title, status=status, due_date=d(due_offset))
    lnk("demo_persons", "tasks", person_id, rid)
    lnk("demo_sale_opportunities", "tasks", opp_id, rid)
    return rid


def meeting(opp_id, title, mtype, days_ago, hour, attendee_ids):
    mid = rec("demo_meetings", title=title, meeting_type=mtype,
              starts_at=dt(-days_ago, hour), status="done")
    lnk("demo_sale_opportunities", "meetings", opp_id, mid)
    lnk("demo_meetings", "attendees", mid, attendee_ids)
    return mid


def assessment(person_id, meeting_id, title, cefr, summary):
    aid = rec("demo_assessments", title=title, cefr_overall=cefr, needs_summary=summary)
    lnk("demo_persons", "assessments", person_id, aid)
    lnk("demo_meetings", "assessments", meeting_id, aid)
    return aid


# ------------------------------------------------------------------ B2C
def seed_b2c():
    print("\n=== B2C: Anna Nowak (szansa otwarta) ===")
    anna = rec("demo_persons", full_name="Anna Nowak", email="anna.nowak@example.com",
               position="Product Manager")
    lead = rec("demo_leads", lead_name="Anna Nowak – formularz", lead_type="B2C",
               lead_source="Google", qualification="SQL", received_at=d(-30))
    lnk("demo_persons", "leads", anna, lead)

    opp = rec("demo_sale_opportunities", name="Anna Nowak – kurs 1:1", segment="B2C",
              stage=ANNA_STAGE, state="open", deal_value=4800)
    lnk("demo_persons", "bought_opportunities", anna, opp)
    lnk("demo_leads", "opportunities", lead, opp)
    # participants celowo PUSTE: powstaje dopiero przy podpisaniu umowy.

    history(opp, [("Nowa", 28), ("Badanie potrzeb", 24), ("Audyt", 17), ("Demo", 6)])

    meeting(opp, "Discovery call: Anna Nowak", "discovery", 24, 10, anna)
    audit = meeting(opp, "Audyt językowy: Anna Nowak", "audit", 17, 14, anna)
    meeting(opp, "Prezentacja propozycji: Anna Nowak", "demo", 6, 11, anna)
    assessment(anna, audit, "Anna Nowak – audyt", "B1",
               "Potrzebuje swobody w rozmowach ze zleceniodawcami z zagranicy; "
               "najsłabsza płynność w mowie.")

    task("Umów discovery call", "done", -28, anna, opp)
    task("Przygotuj ofertę po demo", "todo", 2, anna, opp)


# ------------------------------------------------------------------ B2B
def seed_b2b():
    print("\n=== B2B: Acme Sp. z o.o. (szansa wygrana, 2 z 3 osób szkolonych) ===")
    acme = rec("demo_companies", name="Acme Sp. z o.o.", nip="5252000001")
    marek = rec("demo_persons", full_name="Marek Zieliński", email="marek@acme.example",
                position="CEO")
    ewa = rec("demo_persons", full_name="Ewa Kowalska", email="ewa@acme.example",
              position="Project Manager")
    piotr = rec("demo_persons", full_name="Piotr Wiśniewski", email="piotr@acme.example",
                position="Sales Manager")
    karol = rec("demo_persons", full_name="Karol Mazur", email="karol@acme.example",
                position="Developer")
    lnk("demo_companies", "persons", acme, [marek, ewa, piotr, karol])

    lead = rec("demo_leads", lead_name="Acme – audyty dla 3 pracowników", lead_type="B2B",
               lead_source="Recommendation", qualification="SQL", received_at=d(-30))
    lnk("demo_persons", "leads", marek, lead)

    opp = rec("demo_sale_opportunities", name="Acme – audyty i kurs", segment="B2B",
              stage="Umowa podpisana", state="won", deal_value=9600)
    lnk("demo_companies", "opportunities", acme, opp)
    lnk("demo_persons", "bought_opportunities", marek, opp)
    lnk("demo_leads", "opportunities", lead, opp)
    # Participants = tylko Ewa i Piotr. Marek płaci (kupujący), Karol miał audyt.
    lnk("demo_sale_opportunities", "participants", opp, [ewa, piotr])

    history(opp, [("Nowa", 28), ("Badanie potrzeb", 24), ("Audyt", 18), ("Demo", 9),
                  ("Oferta wysłana", 7), ("Umowa wysłana", 3), ("Umowa podpisana", 1)])

    meeting(opp, "Discovery call: Acme (Marek)", "discovery", 24, 10, marek)
    a_ewa = meeting(opp, "Audyt: Ewa Kowalska", "audit", 18, 9, ewa)
    a_piotr = meeting(opp, "Audyt: Piotr Wiśniewski", "audit", 17, 9, piotr)
    a_karol = meeting(opp, "Audyt: Karol Mazur", "audit", 16, 9, karol)
    meeting(opp, "Prezentacja propozycji: Acme (Marek)", "demo", 9, 15, marek)

    assessment(ewa, a_ewa, "Ewa Kowalska – audyt", "B2",
               "Prowadzi spotkania z klientami z UK; potrzebuje słownictwa "
               "negocjacyjnego.")
    assessment(piotr, a_piotr, "Piotr Wiśniewski – audyt", "B1",
               "Prezentacje handlowe po angielsku; pewność siebie w mowie.")
    assessment(karol, a_karol, "Karol Mazur – audyt", "B1",
               "Głównie pisemna komunikacja z zespołem; nie zapisany na kurs.")

    task("Umów audyt z Karolem", "done", -18, karol, opp)
    task("Fakturowanie: Acme (NIP w firmie)", "todo", 3, marek, opp)
    task("Wróć do Marka w sprawie Karola", "todo", 30, marek, opp)


def load_ids():
    """Id tabel demo_* i id ich pól relacji (po tytule)."""
    tables = core.existing_tables()
    for t in demo.TABLES:
        title = t["title"]
        tid = tables.get(title.lower())
        if not tid:
            sys.exit(f"Brak tabeli {title} - najpierw `make demo-schema-init`.")
        TABLE_IDS[title] = tid
        LINK_FIELDS[title] = {
            c["title"].strip().lower(): c["id"]
            for c in api("GET", f"/api/v2/meta/tables/{tid}").get("columns", [])
            if c.get("uidt") in ("Links", "LinkToAnotherRecord")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="pokaż plan, nie wywołuj API")
    args = ap.parse_args()
    DRY = args.dry_run

    if ANNA_STAGE not in demo.STAGES:
        sys.exit(f"ANNA_STAGE={ANNA_STAGE!r} nie jest jednym z etapów: {demo.STAGES}")
    print(f"NocoDB: {core.URL}, base: {core.BASE_ID}{' [DRY RUN]' if DRY else ''}")
    if not DRY:
        load_ids()
        rows = api("GET", f"/api/v2/tables/{TABLE_IDS['demo_persons']}/records",
                   params={"limit": 1}).get("list", [])
        if rows:
            sys.exit("demo_persons nie jest pusta - usuń wiersze demo (albo tabele "
                     "i uruchom `make demo-schema-init` od nowa), bo skrypt nie "
                     "dedupe'uje.")
    seed_b2c()
    seed_b2b()
    print(f"\nGotowe: {COUNTS['created']} rekordów, {COUNTS['linked']} linków.")
    print("Sprawdź w UI: kanban demo_sale_opportunities po `stage` (Anna: Demo, "
          "otwarta; Acme: Umowa podpisana), karta Marka (kupujący) vs Karola "
          "(attendee audytu, bez participants) vs Ewy (participant).")
