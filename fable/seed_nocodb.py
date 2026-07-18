#!/usr/bin/env python3
"""Seed the CoAction CRM NocoDB base with sample data (records + links).

Matches nocodb_crm_schema_v2.md. Creates a realistic dataset that exercises
every relation type:
  one-to-many : companies -> leads, leads -> participants/meetings/tasks/activities
  many-to-one : meetings -> participant, tasks -> project
  many-to-many: leads <-> testimonials

Usage:
  1. Fill in CONFIG below (URL, API token, base id, team emails).
  2. pip install requests
  3. python3 seed_nocodb.py
Re-running creates duplicates - wipe the tables first if you re-seed.
"""
import sys
from datetime import date, datetime, timedelta

import requests

# ----------------------------------------------------------------- CONFIG
CONFIG = {
    "url": "https://noco.example.com",      # no trailing slash
    "token": "PASTE_NOCODB_API_TOKEN",
    "base_id": "PASTE_BASE_ID",             # p... id, visible in the base URL
    "emails": {
        "przemek": "przemek@example.com",
        "dorota": "dorota@example.com",
        "aleksandra": "aleksandra@example.com",
        "paulina": "paulina@example.com",
        "kasia": "kasia@example.com",
    },
}
# Table titles as created in NocoDB (case-insensitive match):
TABLES = ["companies", "leads", "participants", "meetings",
          "tasks", "task_templates", "projects", "activities", "testimonials"]

S = requests.Session()
S.headers.update({"xc-token": CONFIG["token"], "Content-Type": "application/json"})
BASE = CONFIG["url"].rstrip("/")


def api(method, path, **kw):
    r = S.request(method, f"{BASE}{path}", **kw)
    if not r.ok:
        sys.exit(f"API error {r.status_code} on {method} {path}: {r.text[:500]}")
    return r.json() if r.text else {}


def resolve_meta():
    """Map table titles -> ids and, per table, link-field titles -> field ids."""
    tables, links = {}, {}
    for t in api("GET", f"/api/v2/meta/bases/{CONFIG['base_id']}/tables").get("list", []):
        title = t["title"].strip().lower()
        if title in TABLES:
            tables[title] = t["id"]
    missing = [t for t in TABLES if t not in tables]
    if missing:
        sys.exit(f"Tables not found in base (check titles): {missing}")
    for title, tid in tables.items():
        links[title] = {}
        for col in api("GET", f"/api/v2/meta/tables/{tid}/columns").get("list",
                api("GET", f"/api/v2/meta/tables/{tid}").get("columns", [])):
            if col.get("uidt") in ("Links", "LinkToAnotherRecord"):
                links[title][col["title"].strip().lower()] = col["id"]
    return tables, links


def create(table, record):
    """POST a record, return its Id."""
    res = api("POST", f"/api/v2/tables/{TBL[table]}/records", json=record)
    rid = res.get("Id") or res.get("id") or (res[0].get("Id") if isinstance(res, list) else None)
    print(f"  + {table}: {record.get('name') or record.get('title') or record.get('contact_name') or record.get('full_name') or record.get('summary')} (Id={rid})")
    return rid


def link(table, field, record_id, target_ids):
    """Link record_id.<field> -> target_ids. Verifies the link field exists."""
    fid = LNK[table].get(field)
    if not fid:
        print(f"  ! link field '{field}' not found on '{table}' - skipped "
              f"(available: {list(LNK[table])})")
        return
    ids = target_ids if isinstance(target_ids, list) else [target_ids]
    api("POST", f"/api/v2/tables/{TBL[table]}/links/{fid}/records/{record_id}",
        json=[{"Id": i} for i in ids])
    print(f"    ~ {table}#{record_id}.{field} -> {ids}")


def d(offset):
    return (date.today() + timedelta(days=offset)).isoformat()


def dt(offset, hour):
    return (datetime.now() + timedelta(days=offset)).replace(
        hour=hour, minute=0, second=0, microsecond=0).isoformat()


print("Resolving base metadata...")
TBL, LNK = resolve_meta()
E = CONFIG["emails"]
print(f"Tables: {TBL}\n")

# ----------------------------------------------------------------- projects
print("projects:")
prj_mkt = create("projects", {"name": "Marketing", "team": "marketing", "active": True})
prj_sal = create("projects", {"name": "Sprzedaż", "team": "sales", "active": True})
prj_ops = create("projects", {"name": "Wewnętrzne", "team": "ops", "active": True})

# ----------------------------------------------------------------- companies
print("companies:")
c_techflow = create("companies", {
    "name": "TechFlow Sp. z o.o.", "domains": "techflow.pl, techflow.io",
    "industry": "IT", "size": "51-250",
    "notes": "Software house, ~120 devs. Async-first communication, English used with US clients."})
c_baltic = create("companies", {
    "name": "Baltic Logistics S.A.", "domains": "balticlogistics.pl",
    "industry": "Logistyka", "size": "250+",
    "notes": "Freight forwarding. Formal tone, decisions go through the board."})

# ----------------------------------------------------------------- testimonials
print("testimonials:")
t_it = create("testimonials", {
    "title": "Case study: zespół dev w US-owym projekcie", "client_name": "Anonimizowany software house",
    "industry": "IT", "type": "case_study", "variant": "english_for_it", "active": True,
    "content": "12 developers, 6 months, focus on daily stand-ups and client demos. Avg progress +0.8 CEFR sub-level."})
t_b2c = create("testimonials", {
    "title": "Opinia: awans po roku nauki", "client_name": "Senior Frontend Developer",
    "industry": "IT", "type": "testimonial", "variant": "business_english", "active": True,
    "content": "After a year I finally lead client calls without stress. The audit nailed my real gaps."})
t_log = create("testimonials", {
    "title": "Case study: dział operacji w logistyce", "client_name": "Firma TSL",
    "industry": "Logistyka", "type": "case_study", "variant": "english_business_skills", "active": True,
    "content": "18 participants across 3 groups, focus on negotiations and email correspondence."})

# ----------------------------------------------------------------- LEAD 1: B2C, full pipeline done (the 'Piotr' scenario)
print("lead L1 (B2C, pipeline at draft_ready):")
l1 = create("leads", {
    "contact_name": "Piotr Zieliński", "contact_email": "piotr.zielinski@gmail.com",
    "contact_phone": "+48 600 100 200", "type": "B2C", "owner": E["przemek"],
    "source": "google", "contact_channel": "formularz", "qualification": "SQL",
    "stage": "offer_discussed", "state": "open", "value": 5400,
    "industry": "IT", "offer_prep_status": "draft_ready", "company_match_status": "none",
    "training_goals": "Lead client calls confidently; improve fluency B2.4 -> C1 within 12 months.",
    "notes": "Wants 2x/week evening sessions. Promotion to team lead pending.",
    "offer_sent_at": d(-3)})
link("leads", "selected_testimonials", l1, [t_it, t_b2c])   # many-to-many proof

p1 = create("participants", {
    "full_name": "Piotr Zieliński", "position": "Senior Frontend Developer",
    "cefr_overall": "B2.4", "cefr_range": "B2.5", "cefr_accuracy": "B2.2",
    "cefr_fluency": "B2.3", "cefr_communication": "B2.6",
    "audit_notes": "Strong vocabulary, hesitates under pressure. Articles and conditionals need work.",
    "needs_summary": "Client demos, sprint reviews, small talk with US stakeholders.",
    "assigned_methodologist": E["aleksandra"]})
link("participants", "lead", p1, l1)                        # B2C: lead is also a participant

m1 = create("meetings", {
    "title": "Discovery — Piotr Zieliński", "type": "discovery",
    "starts_at": dt(-4, 14), "ends_at": dt(-4, 15), "owner": E["przemek"],
    "status": "done", "processing_status": "ai_accepted",
    "transcript": "[SAMPLE] Przemek: What situations are hardest? Piotr: Client demos, definitely...",
    "ai_analysis": "[SAMPLE AI DRAFT] Goals: confident client communication. Challenges: fluency under pressure. Suggested: Business English, 2x/week.",
    "notes": "Very motivated, budget confirmed.", "outcome": "Proceed to offer."})
link("meetings", "lead", m1, l1)
link("meetings", "participant", m1, p1)                     # many-to-one proof

# ----------------------------------------------------------------- LEAD 2: B2B, multiple participants & meetings
print("lead L2 (B2B TechFlow, 3 participants):")
l2 = create("leads", {
    "contact_name": "Marta Kowal", "contact_email": "marta.kowal@techflow.pl",
    "contact_phone": "+48 601 200 300", "type": "B2B", "owner": E["przemek"],
    "source": "polecenie", "contact_channel": "email", "qualification": "SQL",
    "stage": "audit", "state": "open", "value": 38000, "industry": "IT",
    "offer_prep_status": "none", "company_match_status": "confirmed",
    "notes": "HR Manager. Buying for the delivery team, she is NOT a participant herself."})
link("leads", "company", l2, c_techflow)                    # company one-to-many proof (1/2)

p2 = create("participants", {"full_name": "Jan Dąbrowski", "position": "Team Lead",
    "assigned_methodologist": E["dorota"], "cefr_overall": "B1.8",
    "audit_notes": "Audit done: fluent but inaccurate; strong motivation."})
p3 = create("participants", {"full_name": "Ola Wrona", "position": "QA Engineer",
    "assigned_methodologist": E["dorota"]})
p4 = create("participants", {"full_name": "Tomasz Lis", "position": "Backend Developer",
    "assigned_methodologist": E["dorota"]})
for p in (p2, p3, p4):
    link("participants", "lead", p, l2)                     # lead one-to-many proof
    link("participants", "company", p, c_techflow)

m2 = create("meetings", {"title": "Discovery — TechFlow (Marta Kowal)", "type": "discovery",
    "starts_at": dt(-10, 10), "owner": E["przemek"], "status": "done",
    "processing_status": "none", "notes": "3 people to audit, budget 35-40k."})
link("meetings", "lead", m2, l2)
m3 = create("meetings", {"title": "Audyt — Jan Dąbrowski", "type": "audit",
    "starts_at": dt(2, 9), "owner": E["dorota"], "status": "scheduled",
    "processing_status": "none"})
link("meetings", "lead", m3, l2)
link("meetings", "participant", m3, p2)

# ----------------------------------------------------------------- LEAD 3: B2C pair (husband + wife)
print("lead L3 (B2C pair):")
l3 = create("leads", {
    "contact_name": "Adam Nowicki", "contact_email": "adam.nowicki@wp.pl",
    "type": "B2C", "owner": E["przemek"], "source": "polecenie",
    "contact_channel": "telefon", "qualification": "MQL", "stage": "new",
    "state": "open", "value": 9600, "offer_prep_status": "none",
    "company_match_status": "none", "notes": "Wants lessons together with his wife."})
p5 = create("participants", {"full_name": "Adam Nowicki", "position": "Accountant",
    "assigned_methodologist": E["aleksandra"]})
p6 = create("participants", {"full_name": "Ewa Nowicka", "position": "Project Manager",
    "assigned_methodologist": E["aleksandra"]})
link("participants", "lead", p5, l3)
link("participants", "lead", p6, l3)                        # 1 lead -> 2 participants

# ----------------------------------------------------------------- LEAD 4: returning company (W5 dedup case)
print("lead L4 (returning company, pending confirmation):")
l4 = create("leads", {
    "contact_name": "Karol Wiśniewski", "contact_email": "karol.wisniewski@techflow.pl",
    "type": "B2B", "owner": E["przemek"], "source": "powrot_klienta",
    "contact_channel": "email", "qualification": "MQL", "stage": "discovery_scheduled",
    "state": "open", "offer_prep_status": "none",
    "company_match_status": "pending_confirmation",
    "notes": "Sales dept this time - different budget owner than Marta's delivery team."})
link("leads", "company", l4, c_techflow)                    # company one-to-many proof (2/2)
m4 = create("meetings", {"title": "Discovery — Karol Wiśniewski (TechFlow sales)",
    "type": "discovery", "starts_at": dt(3, 13), "owner": E["przemek"],
    "status": "scheduled", "processing_status": "none"})
link("meetings", "lead", m4, l4)

# ----------------------------------------------------------------- task templates
print("task_templates:")
tt1 = create("task_templates", {"title": "Raport marketingowy {{month}}",
    "assignee": E["kasia"], "rrule": "FREQ=WEEKLY;BYDAY=MO", "due_offset_days": 1,
    "description": "Weekly channels summary for the CEO.", "active": True})
tt2 = create("task_templates", {"title": "Fakturowanie klientów {{month}}",
    "assignee": E["paulina"], "rrule": "FREQ=MONTHLY;BYMONTHDAY=1", "due_offset_days": 3,
    "description": "Issue invoices for all active trainings.", "active": True})
link("task_templates", "project", tt1, prj_mkt)
link("task_templates", "project", tt2, prj_ops)

# ----------------------------------------------------------------- tasks
print("tasks:")
tasks = [
    ({"title": "Offer draft ready - assemble the offer: Piotr Zieliński", "status": "todo",
      "priority": "high", "assignee": E["przemek"], "created_by_flow": "W6b",
      "description": f"lead:{l1}", "due_date": d(1)}, prj_sal, l1),
    ({"title": "Confirm company match: TechFlow (karol.wisniewski@techflow.pl)", "status": "todo",
      "priority": "normal", "assignee": E["przemek"], "created_by_flow": "W5",
      "description": f"lead:{l4}", "due_date": d(1)}, prj_sal, l4),
    ({"title": "Przygotować audyty dla TechFlow (3 osoby)", "status": "in_progress",
      "priority": "high", "assignee": E["dorota"], "description": f"lead:{l2}",
      "due_date": d(2)}, prj_sal, l2),
    ({"title": "Zadzwonić do Adama Nowickiego - termin discovery", "status": "todo",
      "priority": "normal", "assignee": E["przemek"], "description": f"lead:{l3}",
      "due_date": d(0)}, prj_sal, l3),
    ({"title": "Newsletter lipcowy - draft", "status": "todo", "priority": "normal",
      "assignee": E["kasia"], "due_date": d(4)}, prj_mkt, None),   # no lead: marketing task
    ({"title": "Define training goals: Piotr Zieliński", "status": "done",
      "priority": "normal", "assignee": E["aleksandra"], "created_by_flow": "W6a",
      "description": f"lead:{l1}", "due_date": d(-2)}, prj_sal, l1),
]
for rec, prj, lead_id in tasks:
    tid = create("tasks", rec)
    link("tasks", "project", tid, prj)
    if lead_id:
        link("tasks", "lead", tid, lead_id)
link("tasks", "template", create("tasks", {
    "title": f"Raport marketingowy {date.today().isoformat()[:7]}", "status": "todo",
    "priority": "normal", "assignee": E["kasia"], "created_by_flow": "W1",
    "due_date": d(1)}), tt1)                                # task -> template provenance

# ----------------------------------------------------------------- activities (the 'Piotr' timeline)
print("activities:")
acts = [
    {"summary": "Lead created from Tally form: Piotr Zieliński", "type": "lead_created",
     "flow": "W4", "triggered_by": "system", "payload": f'{{"lead_id": {l1}}}'},
    {"summary": "Task for Przemek: Schedule discovery call", "type": "task_created",
     "flow": "W4", "triggered_by": "system", "payload": f'{{"lead_id": {l1}}}'},
    {"summary": "Transcript pasted, analysis requested", "type": "transcript_added",
     "flow": "W6a", "triggered_by": E["przemek"], "payload": f'{{"meeting_id": {m1}}}'},
    {"summary": "AI analysis ready for meeting: Discovery — Piotr Zieliński",
     "type": "ai_analysis_done", "flow": "W6a", "triggered_by": "system",
     "payload": f'{{"meeting_id": {m1}, "model": "sample", "usage": null}}'},
    {"summary": "AI draft accepted, goals requested (Piotr Zieliński)", "type": "ai_accepted",
     "flow": "W6a", "triggered_by": E["przemek"], "payload": f'{{"meeting_id": {m1}}}'},
    {"summary": "Goals saved, testimonials requested (Piotr Zieliński)", "type": "goals_provided",
     "flow": "W6b", "triggered_by": E["aleksandra"], "payload": f'{{"lead_id": {l1}}}'},
    {"summary": "2 testimonial(s) linked, offer draft ready (Piotr Zieliński)",
     "type": "testimonials_provided", "flow": "W6b", "triggered_by": E["przemek"],
     "payload": f'{{"lead_id": {l1}, "linked": 2}}'},
    {"summary": "Company match suggested: TechFlow Sp. z o.o. (techflow.pl)",
     "type": "company_match_suggested", "flow": "W5", "triggered_by": "system",
     "payload": f'{{"lead_id": {l4}, "company_id": {c_techflow}}}'},
]
for a in acts:
    aid = create("activities", a)
    link("activities", "lead", aid, l4 if a["type"] == "company_match_suggested" else l1)

print("\nDone. Open the base and verify:")
print("  - companies/TechFlow shows 2 leads (Marta, Karol)  -> one-to-many")
print("  - leads/L2 shows 3 participants                    -> one-to-many")
print("  - leads/L1 shows 2 testimonials, testimonial T1 shows L1 back -> many-to-many")
print("  - meetings/Audyt shows exactly 1 participant       -> many-to-one")
print("  - activities filtered by L1 read as the Piotr timeline")
