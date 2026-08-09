#!/usr/bin/env python3
r"""Seeduje przez NocoDB REST API 13 tabel CRM, których NIE dotyka
`seed-service` (ten zasila tylko `leads`/`companies`/`participants` z
`init-data/Statusy_z_CRM_filled.xlsx` - patrz
`seed-service/seed_app.py`). Do szybkiego ręcznego testowania reszty
pipeline'u (meetings -> assessments -> recommendations -> offers, taski,
log activities), NIE do produkcji.

Tabele:
  referencyjne (dedupe po nazwie, bezpieczne do wielokrotnego uruchamiania):
    pricing, testimonials, training_descriptions, recommendation_packages,
    document_templates, projects, task_templates
  wpięte pod ISTNIEJĄCE leady/participants (pobrane z bazy - patrz
  --leads), NIE dedupe'owane - kolejne uruchomienie dokłada kolejną porcję:
    meetings, assessments, recommendations, offers, tasks, activities

Skąd biorą się leady/participants do wpięcia: ten skrypt niczego nie
generuje sam - czyta `n` istniejących rekordów `leads` (najlepiej po
`make init-data`/seed-service) i ich linki `participants`, potem dokleja pod
nie meetings/assessments/etc. Jeśli baza jest pusta (0 leadów), sensowna
jest tylko część referencyjna - reszta zostanie pominięta z ostrzeżeniem.

Pola SingleSelect/MultiSelect MUSZĄ zgadzać się z listami opcji z
`scripts/init-schema.py` (TABLES) - stałe niżej są stamtąd świadomie
skopiowane, nie zaimportowane (import tamtego modułu ma efekty uboczne:
sys.exit przy braku NC_API_TOKEN/NC_CRM_BASE_ID w chwili importu). Jeśli
zmienisz listę opcji w init-schema.py, zmień ją i tu.

Pola typu User (owner/assignee/assigned_methodologist) - jeśli chcesz je
wypełnić, ustaw SEED_TEAM_EMAILS (comma-separated) w .env; bez tego skrypt
świadomie zostawia je puste zamiast wpisywać czyjś prywatny e-mail na sztywno
(tak jak robił to nieaktualny docs/archive/fable/seed_nocodb.py).

Wymaga w środowisku (patrz .env.example): NC_API_TOKEN, NC_CRM_BASE_ID.
Opcjonalnie: NC_LOCAL_URL (default http://localhost:8081), SEED_TEAM_EMAILS.

Usage:
  make seed-extra
  # albo bezpośrednio:
  set -a; source .env; set +a
  python3 scripts/seed-extra.py --dry-run
  python3 scripts/seed-extra.py --leads 12
  python3 scripts/seed-extra.py --leads 12 --skip-reference   # tylko dane pod leady
"""
import argparse
import os
import random
import sys
from datetime import date, datetime, timedelta

import requests

URL = os.environ.get("NC_LOCAL_URL", "http://localhost:8081").rstrip("/")
TOKEN = os.environ.get("NC_API_TOKEN")
BASE_ID = os.environ.get("NC_CRM_BASE_ID")
TEAM_EMAILS = [e.strip() for e in os.environ.get("SEED_TEAM_EMAILS", "").split(",") if e.strip()]

if not TOKEN or not BASE_ID:
    sys.exit("Brak NC_API_TOKEN / NC_CRM_BASE_ID w środowisku - patrz .env.example.")

S = requests.Session()
S.headers.update({"xc-token": TOKEN, "Content-Type": "application/json"})


def api(method, path, **kw):
    try:
        r = S.request(method, f"{URL}{path}", timeout=30, **kw)
    except requests.RequestException as e:
        sys.exit(f"Nie mogę się połączyć z NocoDB ({URL}): {type(e).__name__}.")
    if not r.ok:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
    return r.json() if r.text else {}


# --------------------------------------------------------------- stałe list opcji
# Skopiowane z scripts/init-schema.py - patrz uwaga w docstringu wyżej. UWAGA:
# testimonials.variant to WŁASNA, INNA lista opcji niż VARIANT (offers.product_type
# / pricing.product) - nie mylić, mimo tej samej nazwy pola.
MODE = ("1-1", "w_parach", "grupa")
VARIANT = ("standard", "intensive_workshop", "oferta_specjalna",
           "audyt_jezykowy", "job_interview", "webinar")
TESTIMONIAL_VARIANT = ("business_english", "english_for_it", "english_business_skills")

TABLES_NEEDED = ["leads", "participants", "meetings", "assessments",
                 "recommendations", "training_descriptions",
                 "recommendation_packages", "pricing", "offers",
                 "document_templates", "testimonials", "projects",
                 "task_templates", "tasks", "activities"]


def resolve_meta():
    """Mapuje tytuły tabel -> id oraz, per tabela, tytuły pól Links -> id pola."""
    tables, links = {}, {}
    all_tables = api("GET", f"/api/v2/meta/bases/{BASE_ID}/tables").get("list", [])
    by_title = {t["title"].strip().lower(): t for t in all_tables}
    missing = [t for t in TABLES_NEEDED if t not in by_title]
    if missing:
        sys.exit(f"Brakuje tabel w bazie (uruchom najpierw `make init-schema`): {missing}")
    for title in TABLES_NEEDED:
        tid = by_title[title]["id"]
        tables[title] = tid
        links[title] = {}
        for col in api("GET", f"/api/v2/meta/tables/{tid}").get("columns", []):
            if col.get("uidt") in ("Links", "LinkToAnotherRecord"):
                links[title][col["title"].strip().lower()] = col["id"]
    return tables, links


def rnd_owner():
    return random.choice(TEAM_EMAILS) if TEAM_EMAILS else None


def clean(record):
    return {k: v for k, v in record.items() if v is not None}


COUNTS = {"created": 0, "linked": 0, "skipped_existing": 0, "errors": 0}


def create(table_title, tables, record, dry_run, label=None):
    record = clean(record)
    tag = label or record.get("title") or record.get("name") or record.get("summary") or "?"
    if dry_run:
        print(f"  + [dry-run] {table_title}: {tag}")
        return f"<{table_title}:{tag}>"
    try:
        res = api("POST", f"/api/v2/tables/{tables[table_title]}/records", json=record)
        rid = res.get("Id") or (res[0].get("Id") if isinstance(res, list) else None)
        COUNTS["created"] += 1
        print(f"  + {table_title}: {tag} (Id={rid})")
        return rid
    except RuntimeError as e:
        COUNTS["errors"] += 1
        print(f"  ! {table_title}: {tag} -> {e}")
        return None


def find_by_field(table_title, tables, field, value, dry_run):
    if dry_run:
        return None
    res = api("GET", f"/api/v2/tables/{tables[table_title]}/records",
              params={"where": f"({field},eq,{value})", "limit": 1})
    rows = res.get("list", [])
    return rows[0]["Id"] if rows else None


def find_or_create(table_title, tables, dedupe_field, record, dry_run, label=None):
    """Dla tabel referencyjnych: pomija insert, jeśli rekord o tej samej
    wartości `dedupe_field` już istnieje - bezpieczne do wielokrotnego
    uruchamiania, w przeciwieństwie do tabel wpiętych pod leady."""
    existing = find_by_field(table_title, tables, dedupe_field, record[dedupe_field], dry_run)
    if existing:
        COUNTS["skipped_existing"] += 1
        print(f"  = {table_title}: {record[dedupe_field]} już istnieje (Id={existing}), pomijam")
        return existing
    return create(table_title, tables, record, dry_run, label=label)


def link(table_title, field_title, links, tables, owner_id, target_ids, dry_run):
    field_id = links.get(table_title, {}).get(field_title.lower())
    if not field_id:
        print(f"  ! link {table_title}.{field_title}: pole nie znalezione, pomijam "
              f"(dostępne: {list(links.get(table_title, {}))})")
        return
    if owner_id is None or not target_ids:
        return
    ids = target_ids if isinstance(target_ids, list) else [target_ids]
    ids = [i for i in ids if i is not None]
    if not ids:
        return
    if dry_run:
        print(f"    ~ [dry-run] {table_title}#{owner_id}.{field_title} -> {ids}")
        return
    api("POST", f"/api/v2/tables/{tables[table_title]}/links/{field_id}/records/{owner_id}",
        json=[{"Id": i} for i in ids])
    COUNTS["linked"] += 1
    print(f"    ~ {table_title}#{owner_id}.{field_title} -> {ids}")


# --------------------------------------------------------------- czas
def d(offset_days):
    return (date.today() + timedelta(days=offset_days)).isoformat()


def dt(offset_days, hour):
    return (datetime.now() + timedelta(days=offset_days)).replace(
        hour=hour, minute=0, second=0, microsecond=0).isoformat()


# --------------------------------------------------------------- dane referencyjne
def seed_reference(tables, links, dry_run):
    print("\n--- pricing ---")
    # pricing nie ma naturalnego pola-nazwy do dedupe po jednej kolumnie
    # (product+mode+hours razem tworzą klucz) - insert wprost, mała tabela
    # referencyjna, bezpiecznie wyczyścić ręcznie przy re-seedzie jeśli
    # duplikaty przeszkadzają.
    pricing_rows = []
    for product in ("standard", "intensive_workshop", "audyt_jezykowy"):
        for mode in MODE:
            for hours, price in ((30, 4500), (60, 8400), (90, 11700)):
                pricing_rows.append({
                    "product": product, "training_group_size": mode, "hours": hours,
                    "total_price": price, "valid_from": d(-365), "valid_to": None,
                })
    for row in pricing_rows:
        create("pricing", tables, row, dry_run,
               label=f"{row['product']}/{row['training_group_size']}/{row['hours']}h")

    print("\n--- testimonials ---")
    testimonial_rows = [
        {"title": "Case study: zespół dev w projekcie US", "client_name": "Software house (anonim.)",
         "position": "Engineering Manager", "industry": "IT", "type": "case_study",
         "variant": "business_english", "active": True,
         "content": "12 developerów, 6 miesięcy, focus na daily standupy i demo dla klienta."},
        {"title": "Opinia: pewniejsze call'e z klientem", "client_name": "Senior Frontend Developer",
         "position": "Senior Frontend Developer", "industry": "IT", "type": "testimonial",
         "variant": "business_english", "active": True,
         "content": "Po roku prowadzę call'e z klientem bez stresu, audyt trafił w realne braki."},
        {"title": "Case study: dział operacji w logistyce", "client_name": "Firma TSL",
         "position": "Operations Director", "industry": "Transport/Logistics", "type": "case_study",
         "variant": "english_business_skills", "active": True,
         "content": "18 uczestników w 3 grupach, negocjacje i korespondencja mailowa."},
        {"title": "Opinia: przygotowanie do rozmowy rekrutacyjnej", "client_name": "Kandydat B2C",
         "position": "Backend Developer", "industry": "IT", "type": "testimonial",
         "variant": "english_for_it", "active": True,
         "content": "3 sesje przed rozmową w międzynarodowej firmie - dostał ofertę."},
    ]
    for row in testimonial_rows:
        assert row["variant"] in TESTIMONIAL_VARIANT, f"nieznana opcja variant: {row['variant']}"
        find_or_create("testimonials", tables, "title", row, dry_run)

    print("\n--- document_templates ---")
    for row in [
        {"name": "Oferta standard PL", "kind": "offer", "active": True,
         "notes": "Domyślny szablon PPTX dla ofert standard/intensive_workshop."},
        {"name": "Raport audytu jezykowego", "kind": "audit_report", "active": True,
         "notes": "Szablon raportu CEFR generowany po assessments."},
    ]:
        find_or_create("document_templates", tables, "name", row, dry_run)

    print("\n--- training_descriptions ---")
    training_rows = [
        {"title": "Business English - fundamenty", "training_type": "business_english",
         "learning_goal": "Pewne prowadzenie spotkań i korespondencji po angielsku.",
         "description": "Moduł bazowy: słownictwo biznesowe, e-mail, small talk.",
         "hours_in_package": 30, "active": True},
        {"title": "English for IT - code review i demo", "training_type": "english_for_it",
         "learning_goal": "Swobodne code review, demo i rozmowy z zespołem rozproszonym.",
         "description": "Słownictwo techniczne, prowadzenie demo, komunikacja async.",
         "hours_in_package": 30, "active": True},
        {"title": "Warsztat: negocjacje handlowe", "training_type": "workshop_negocjacje",
         "learning_goal": "Skuteczne negocjacje warunków z klientem zagranicznym.",
         "description": "Warsztat intensywny, symulacje negocjacyjne.",
         "hours_in_package": 15, "active": True},
        {"title": "Warsztat: facylitacja spotkań", "training_type": "workshop_facylitacja",
         "learning_goal": "Prowadzenie spotkań międzynarodowych zespołów.",
         "description": "Struktura spotkania, moderacja dyskusji, follow-up.",
         "hours_in_package": 15, "active": True},
    ]
    training_ids = {}
    for row in training_rows:
        tid = find_or_create("training_descriptions", tables, "title", row, dry_run)
        training_ids[row["title"]] = tid

    print("\n--- recommendation_packages ---")
    package_rows = [
        ("Ścieżka: Business English 1-1", 1, 60, "1-1", "Business English - fundamenty"),
        ("Ścieżka: English for IT w parach", 1, 60, "w_parach", "English for IT - code review i demo"),
        ("Ścieżka: warsztat negocjacyjny grupowy", 1, 15, "grupa", "Warsztat: negocjacje handlowe"),
    ]
    for name, sort_order, hours, mode, training_title in package_rows:
        pkg_id = find_or_create("recommendation_packages", tables, "package_name", {
            "package_name": name, "sort_order": sort_order,
            "hours_in_package": hours, "training_group_size": mode,
        }, dry_run)
        link("training_descriptions", "recommendation_packages", links, tables,
             training_ids.get(training_title), pkg_id, dry_run)


def get_recommendation_package_ids(tables, dry_run):
    if dry_run:
        return []
    res = api("GET", f"/api/v2/tables/{tables['recommendation_packages']}/records", params={"limit": 25})
    return [r["Id"] for r in res.get("list", [])]


def get_project_and_template_ids(tables, links, dry_run):
    print("\n--- projects ---")
    project_ids = {}
    for row in [{"name": "Sprzedaż", "team": "sales", "active": True},
                {"name": "Marketing", "team": "marketing", "active": True}]:
        project_ids[row["name"]] = find_or_create("projects", tables, "name", row, dry_run)

    print("\n--- task_templates ---")
    tt_rows = [
        {"title": "Follow-up po discovery", "rrule": "", "due_offset_days": 2,
         "description": "Zadzwoń/napisz, jeśli lead nie odpowiedział 2 dni po discovery.",
         "assignee": rnd_owner(), "active": True},
        {"title": "Przygotuj audyt", "rrule": "", "due_offset_days": 3,
         "description": "Umów i przeprowadź audyt CEFR dla uczestnika.",
         "assignee": rnd_owner(), "active": True},
    ]
    tt_ids = {}
    for row in tt_rows:
        tid = find_or_create("task_templates", tables, "title", row, dry_run)
        tt_ids[row["title"]] = tid
        link("projects", "task_templates", links, tables, project_ids.get("Sprzedaż"), tid, dry_run)
    return project_ids, tt_ids


# --------------------------------------------------------------- dane wpięte pod leady
def fetch_leads_with_participants(tables, links, n, dry_run):
    if dry_run:
        print(f"\n[dry-run] pobrałbym do {n} leadów + ich participants z bazy - "
              f"pomijam, bo dry-run nie modyfikuje ani nie zależy od realnych ID.")
        return []
    leads_id = tables["leads"]
    resp = api("GET", f"/api/v2/tables/{leads_id}/records", params={"limit": max(n * 3, 30)})
    leads = resp.get("list", [])
    if not leads:
        print("\n⚠️  Brak leadów w bazie - pomijam meetings/assessments/recommendations/"
              "offers/tasks/activities (uruchom najpierw seed-service / make init-data).")
        return []
    random.shuffle(leads)
    picked = []
    participants_field_id = links.get("leads", {}).get("participants")
    for lead_rec in leads[:n]:
        participants = []
        if participants_field_id:
            pres = api("GET", f"/api/v2/tables/{leads_id}/links/{participants_field_id}"
                              f"/records/{lead_rec['Id']}", params={"limit": 5})
            participants = pres.get("list", [])
        picked.append((lead_rec, participants))
    return picked


def lead_display_name(lead_rec):
    return lead_rec.get("lead_name") or f"lead#{lead_rec.get('Id')}"


def seed_per_lead(tables, links, leads_with_participants, package_ids, project_ids, tt_ids, dry_run):
    projects = [pid for pid in project_ids.values() if pid]
    templates = [tid for tid in tt_ids.values() if tid]

    for lead_rec, participants in leads_with_participants:
        lead_id = lead_rec["Id"]
        name = lead_display_name(lead_rec)
        print(f"\n--- lead: {name} (Id={lead_id}) ---")

        # meeting
        meeting_type = random.choice(["discovery", "audit", "needs_analysis", "offer_discussion"])
        meeting_day_offset = -random.randint(1, 20)
        meeting_id = create("meetings", tables, {
            "title": f"{meeting_type.capitalize()} — {name}",
            "meeting_type": meeting_type, "starts_at": dt(meeting_day_offset, 10),
            "ends_at": dt(meeting_day_offset, 11), "owner": rnd_owner(),
            "status": "done", "notes": "[seed-extra] dane testowe.",
            "goals": "Pewniejsza komunikacja w rozmowach z klientami zagranicznymi.",
            "challenges": "Stres pod presją czasu, wahanie w gramatyce.",
            "ai_status": "ai_accepted", "outcome": "Proceed to offer.",
        }, dry_run)
        link("leads", "meetings", links, tables, lead_id, meeting_id, dry_run)

        # activities: lead_created + meeting-related
        act_created = create("activities", tables, {
            "summary": f"[seed-extra] Lead w pipeline: {name}", "type": "lead_created",
            "flow": "seed-extra", "triggered_by": "seed-extra",
            "payload": f'{{"lead_id": {lead_id}}}',
        }, dry_run)
        link("leads", "activities", links, tables, lead_id, act_created, dry_run)
        act_meeting = create("activities", tables, {
            "summary": f"[seed-extra] Spotkanie zarejestrowane: {name}",
            "type": "meeting_created", "flow": "seed-extra", "triggered_by": "seed-extra",
            "payload": f'{{"meeting_id": {meeting_id}}}',
        }, dry_run)
        link("leads", "activities", links, tables, lead_id, act_meeting, dry_run)
        link("meetings", "activities", links, tables, meeting_id, act_meeting, dry_run)

        # participants: assessment + recommendation each
        for p in participants:
            p_id, p_name = p["Id"], p.get("full_name", f"participant#{p['Id']}")
            assessment_id = create("assessments", tables, {
                "title": f"Audyt CEFR — {p_name}",
                "assessed_at": d(-random.randint(1, 15)),
                "cefr_overall": random.choice(["B1.5", "B2.2", "B2.6", "C1.1"]),
                "cefr_range": "B2.5", "cefr_accuracy": "B2.2", "cefr_fluency": "B2.3",
                "cefr_communication": "B2.6",
                "strengths": "Bogate słownictwo, dobra wymowa.",
                "gaps": "Czasy złożone, artykuły.",
                "needs_summary": "Rozmowy z klientem, prezentacje dla zarządu.",
                "ai_status": "ai_accepted",
            }, dry_run)
            link("participants", "assessments", links, tables, p_id, assessment_id, dry_run)
            link("meetings", "assessments", links, tables, meeting_id, assessment_id, dry_run)
            link("participants", "meetings", links, tables, p_id, meeting_id, dry_run)

            rec_id = create("recommendations", tables, {
                "title": f"Rekomendacja — {p_name}",
                "type": random.choice(["business_english", "english_plus_skills", "skills_only"]),
                "headline": "Business English, tryb 1-1, 60h",
                "rationale": "Priorytet: pewność w rozmowach z klientem zagranicznym.",
                "priority": random.choice(["wysoki", "sredni", "niski"]),
                "ai_status": "ai_accepted",
            }, dry_run)
            link("participants", "recommendations", links, tables, p_id, rec_id, dry_run)
            if package_ids:
                link("recommendations", "packages", links, tables, rec_id,
                     random.sample(package_ids, k=min(2, len(package_ids))), dry_run)

        # offer
        offer_id = create("offers", tables, {
            "title": f"Oferta — {name}", "status": random.choice(["draft", "sent", "accepted"]),
            "total_price": random.choice([8400, 11700, 16500]),
            "hours": random.choice([30, 60, 90]),
            "product_type": random.choice(VARIANT),
            "version": 1, "template_name": "Oferta standard PL",
            "sent_at": d(-random.randint(0, 10)),
            "valid_until": d(random.randint(10, 30)),
        }, dry_run)
        link("leads", "offers", links, tables, lead_id, offer_id, dry_run)

        # task
        task_id = create("tasks", tables, {
            "title": f"Follow-up: {name}", "assignee": rnd_owner(),
            "due_date": d(random.randint(1, 7)),
            "status": random.choice(["todo", "in_progress"]),
            "priority": random.choice(["normal", "high"]),
            "description": f"[seed-extra] lead:{lead_id}",
            "created_by_flow": "seed-extra",
        }, dry_run)
        link("leads", "tasks", links, tables, lead_id, task_id, dry_run)
        if projects:
            link("projects", "tasks", links, tables, random.choice(projects), task_id, dry_run)
        if templates:
            link("task_templates", "tasks", links, tables, random.choice(templates), task_id, dry_run)
        act_task = create("activities", tables, {
            "summary": f"[seed-extra] Task utworzony: {name}", "type": "task_created",
            "flow": "seed-extra", "triggered_by": "seed-extra",
            "payload": f'{{"lead_id": {lead_id}, "task_id": {task_id}}}',
        }, dry_run)
        link("leads", "activities", links, tables, lead_id, act_task, dry_run)
        link("tasks", "activities", links, tables, task_id, act_task, dry_run)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="pokaż plan, nie wywołuj API (POST)")
    ap.add_argument("--leads", type=int, default=12,
                    help="ile istniejących leadów wykorzystać do meetings/assessments/"
                         "recommendations/offers/tasks/activities (default: 12)")
    ap.add_argument("--skip-reference", action="store_true",
                    help="pomiń pricing/testimonials/training_descriptions/"
                         "recommendation_packages/document_templates/projects/task_templates")
    ap.add_argument("--seed", type=int, default=None, help="ziarno losowości (reprodukowalność)")
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    print(f"NocoDB: {URL}, base: {BASE_ID}{' [DRY RUN]' if args.dry_run else ''}")
    if not TEAM_EMAILS:
        print("ℹ️  SEED_TEAM_EMAILS nie ustawione - pola User (owner/assignee) zostaną puste.")

    tables, links = resolve_meta()

    package_ids, project_ids, tt_ids = [], {}, {}
    if not args.skip_reference:
        seed_reference(tables, links, args.dry_run)
        package_ids = get_recommendation_package_ids(tables, args.dry_run)
        project_ids, tt_ids = get_project_and_template_ids(tables, links, args.dry_run)
    else:
        print("\n(pominięto dane referencyjne: --skip-reference)")
        package_ids = get_recommendation_package_ids(tables, args.dry_run)

    leads_with_participants = fetch_leads_with_participants(tables, links, args.leads, args.dry_run)
    seed_per_lead(tables, links, leads_with_participants, package_ids, project_ids, tt_ids, args.dry_run)

    print(f"\n--- podsumowanie {'(dry-run, nic nie zapisano)' if args.dry_run else ''} ---")
    print(f"utworzone rekordy: {COUNTS['created']}")
    print(f"linki:             {COUNTS['linked']}")
    print(f"pominięte (już istniały): {COUNTS['skipped_existing']}")
    print(f"błędy:             {COUNTS['errors']}")


if __name__ == "__main__":
    main()
