"""E2E tests for the deterministic (AUTO) cases from test_cases.md.

Each test posts a synthetic webhook payload to the TEST copy of a workflow
and asserts the resulting records in the CRM-TEST base. IDs in test names
map 1:1 to the catalog.
"""
from datetime import date

from .conftest import booking, cf7, nc_insert, nc_update, tally

TODAY = date.today().isoformat()
OWNER = {"email": "przemek@example.com"}   # must be a member of the TEST base


def make_lead(nc, **kw):
    rec = {"contact_name": "Test Lead", "contact_email": "t@none.invalid",
           "stage": "new", "state": "open", "type": "B2C",
           "offer_prep_status": "none", "company_match_status": "none",
           "duplicate_check": "none", "enquiry_no": 1}
    rec.update(kw)
    return nc.create("leads", rec)


# ================================================================ W2
def test_W2_01_offer_sent_sets_milestone(nc, hook):
    lid = make_lead(nc)
    row = {"Id": lid, "stage": "offer_sent", "owner": OWNER,
           "contact_name": "Test Lead"}
    hook("w2-stage-change", nc_update(row, {**row, "stage": "new"}))
    nc.wait_for("activities", "(type,eq,stage_changed)")
    lead = nc.get("leads", lid)
    assert str(lead.get("offer_sent_at", ""))[:10] == TODAY
    acts = nc.get_links("activities", "lead",
                        nc.list("activities", "(type,eq,stage_changed)")[0]["Id"])
    assert acts and acts[0]["Id"] == lid          # X-01: activity linked to lead


def test_W2_02_contract_signed_wins(nc, hook):
    lid = make_lead(nc)
    row = {"Id": lid, "stage": "contract_signed", "owner": OWNER,
           "contact_name": "Test Lead"}
    hook("w2-stage-change", nc_update(row, {**row, "stage": "offer_discussed"}))
    nc.wait_for("activities", "(type,eq,stage_changed)")
    lead = nc.get("leads", lid)
    assert lead["state"] == "won" and str(lead.get("closed_at", ""))[:10] == TODAY


def test_W2_03_lost_without_reason_creates_task(nc, hook):
    lid = make_lead(nc)
    row = {"Id": lid, "stage": "lost", "owner": OWNER, "contact_name": "Test Lead"}
    hook("w2-stage-change", nc_update(row, {**row, "stage": "new"}))
    tasks = nc.wait_for("tasks", "(title,like,Fill in loss reason%)")
    assert tasks[0]["priority"] == "high"


def test_W2_04_lost_with_reason_no_task(nc, hook):
    lid = make_lead(nc)
    row = {"Id": lid, "stage": "lost", "loss_reason": "cena", "owner": OWNER,
           "contact_name": "Test Lead"}
    hook("w2-stage-change", nc_update(row, {**row, "stage": "new"}))
    nc.wait_for("activities", "(type,eq,stage_changed)")
    nc.wait_quiet("tasks", "(title,like,Fill in loss reason%)")


def test_W2_05_no_stage_change_is_noop(nc, hook):
    lid = make_lead(nc)
    row = {"Id": lid, "stage": "new", "notes": "edited", "owner": OWNER}
    hook("w2-stage-change", nc_update(row, {**row, "notes": "old"}))
    nc.wait_quiet("activities", "(type,eq,stage_changed)")


def test_W2_06_missing_previous_rows_is_noop(nc, hook):
    lid = make_lead(nc)
    hook("w2-stage-change",
         {"type": "records.after.update",
          "data": {"rows": [{"Id": lid, "stage": "new"}]}})   # no previous_rows
    nc.wait_quiet("activities", "(type,eq,stage_changed)")


# ================================================================ W3
def test_W3_01_new_task_notifies(nc, hook):
    row = {"Id": 999, "title": "Zrób coś", "assignee": OWNER, "due_date": TODAY}
    hook("w3-task-notify", nc_insert(row))
    nc.wait_for("activities", "(type,eq,notification_sent)")


def test_W3_03_same_assignee_update_is_noop(nc, hook):
    row = {"Id": 999, "title": "Zrób coś", "assignee": OWNER}
    hook("w3-task-notify", nc_update(row, dict(row)))
    nc.wait_quiet("activities", "(type,eq,notification_sent)")


def test_W3_04_no_assignee_is_noop(nc, hook):
    hook("w3-task-notify", nc_insert({"Id": 999, "title": "Bez właściciela"}))
    nc.wait_quiet("activities", "(type,eq,notification_sent)")


# ================================================================ W4 v2 (deterministic tiers)
def test_W4_01_tier5_plain_new_lead(nc, hook):
    hook("w4-tally-intake", tally("Nowa Osoba", "nowa@gmail.com", message="krótko"))
    leads = nc.wait_for("leads", "(contact_email,eq,nowa@gmail.com)")
    assert leads[0]["type"] == "B2C" and leads[0]["enquiry_no"] == 1
    nc.wait_for("tasks", "(title,like,Zaklasyfikuj%)")


def test_W4_02_tier1_open_no_new_lead(nc, hook):
    lid = make_lead(nc, contact_email="anna@firma.pl", contact_name="Anna Test",
                    owner="przemek@example.com")
    hook("w4-tally-intake", tally("Anna Test", "anna@firma.pl", message="dopytuję"))
    nc.wait_for("tasks", "(title,like,Klient napisał ponownie%)")
    assert len(nc.list("leads")) == 1              # still exactly one lead
    assert nc.list("leads")[0]["Id"] == lid


def test_W4_03_tier1_closed_new_opportunity(nc, hook):
    old = make_lead(nc, contact_email="ret@firma.pl", contact_name="Powracający K.",
                    state="won", stage="contract_signed")
    hook("w4-tally-intake", tally("Powracający K.", "ret@firma.pl", message="wracam"))
    leads = nc.wait_for("leads", "(contact_email,eq,ret@firma.pl)", count=2)
    new = [l for l in leads if l["Id"] != old][0]
    assert new["enquiry_no"] == 2 and new["source"] == "powrot_klienta"


def test_W4_05_tier3_diacritics_name_match(nc, hook):
    cand = make_lead(nc, contact_name="Michal Kowalski",
                     contact_email="mk@none.invalid")
    hook("w4-tally-intake", tally("Michał Kowalski", "inny@gmail.com"))
    leads = nc.wait_for("leads", "(duplicate_check,eq,pending_confirmation)")
    assert nc.get_links("leads", "possible_duplicate", leads[0]["Id"])[0]["Id"] == cand
    nc.wait_for("tasks", "(title,like,Potwierdź dopasowanie%)")


def test_W4_06_tier3_phone_format_match(nc, hook):
    make_lead(nc, contact_name="Ktoś Zupełnie Inny", contact_phone="600100200",
              contact_email="x@none.invalid")
    hook("w4-tally-intake", tally("Nowe Nazwisko", "y@gmail.com", phone="+48 600-100-200"))
    nc.wait_for("leads", "(duplicate_check,eq,pending_confirmation)")


def test_W4_07_short_name_no_tier3(nc, hook):
    make_lead(nc, contact_name="Jan", contact_email="jan@none.invalid")
    hook("w4-tally-intake", tally("Jan", "z@gmail.com", message="hej"))
    nc.wait_for("tasks", "(title,like,Zaklasyfikuj%)")       # fell through to tier5
    assert not nc.list("leads", "(duplicate_check,eq,pending_confirmation)")


def test_W4_10_cf7_adapter_mapping(nc, hook):
    hook("w4-cf7-intake", cf7("Osoba CF7", "cf7@gmail.com", message="hej"))
    leads = nc.wait_for("leads", "(contact_email,eq,cf7@gmail.com)")
    assert leads[0]["contact_name"] == "Osoba CF7"


def test_W4_11_booking_creates_linked_meeting(nc, hook):
    hook("w4-bookings-intake", booking("Rezerwujący Nowy", "rez@gmail.com"))
    meetings = nc.wait_for("meetings", "(status,eq,scheduled)")
    lead = nc.wait_for("leads", "(contact_email,eq,rez@gmail.com)")[0]
    assert nc.get_links("meetings", "lead", meetings[0]["Id"])[0]["Id"] == lead["Id"]


def test_W4_12_booking_attaches_to_open_lead(nc, hook):
    lid = make_lead(nc, contact_email="known@firma.pl", contact_name="Znany Klient")
    hook("w4-bookings-intake", booking("Znany Klient", "known@firma.pl"))
    meetings = nc.wait_for("meetings", "(status,eq,scheduled)")
    assert nc.get_links("meetings", "lead", meetings[0]["Id"])[0]["Id"] == lid
    assert len(nc.list("leads")) == 1


# ================================================================ W5
def test_W5_01_domain_match_suggests_company(nc, hook):
    cid = nc.create("companies", {"name": "TechFlow", "domains": "techflow.pl"})
    lid = make_lead(nc, contact_email="nowy@techflow.pl", type="B2B")
    hook("w5-company-dedup", nc_insert(
        {"Id": lid, "contact_email": "nowy@techflow.pl", "contact_name": "Nowy",
         "owner": OWNER}))
    nc.wait_for("activities", "(type,eq,company_match_suggested)")
    assert nc.get("leads", lid)["company_match_status"] == "pending_confirmation"
    assert nc.get_links("leads", "company", lid)[0]["Id"] == cid


def test_W5_02_public_domain_noop(nc, hook):
    lid = make_lead(nc, contact_email="ktos@gmail.com")
    hook("w5-company-dedup", nc_insert(
        {"Id": lid, "contact_email": "ktos@gmail.com", "owner": OWNER}))
    nc.wait_quiet("activities", "(type,eq,company_match_suggested)")


def test_W5_05_substring_domain_no_false_match(nc, hook):
    nc.create("companies", {"name": "TechFlow", "domains": "techflow.pl"})
    lid = make_lead(nc, contact_email="ktos@flow.pl")
    hook("w5-company-dedup", nc_insert(
        {"Id": lid, "contact_email": "ktos@flow.pl", "owner": OWNER}))
    nc.wait_quiet("activities", "(type,eq,company_match_suggested)")


def test_W5_06_already_linked_company_noop(nc, hook):
    cid = nc.create("companies", {"name": "TechFlow", "domains": "techflow.pl"})
    lid = make_lead(nc, contact_email="x@techflow.pl")
    nc.link("leads", "company", lid, cid)
    hook("w5-company-dedup", nc_insert(
        {"Id": lid, "contact_email": "x@techflow.pl", "company": 1, "owner": OWNER}))
    nc.wait_quiet("activities", "(type,eq,company_match_suggested)")


# ================================================================ W6a (deterministic branches)
def make_meeting(nc, lid, **kw):
    rec = {"title": "Discovery — Test", "type": "discovery", "status": "done",
           "processing_status": "none", "owner": OWNER["email"]}
    rec.update(kw)
    mid = nc.create("meetings", rec)
    nc.link("meetings", "lead", mid, lid)
    return mid


def test_W6a_02_missing_transcript_errors(nc, hook):
    lid = make_lead(nc)
    mid = make_meeting(nc, lid)
    row = {"Id": mid, "title": "Discovery — Test", "processing_status":
           "analysis_pending", "transcript": "za krótko", "owner": OWNER}
    hook("w6a-meeting-ai", nc_update(row, {**row, "processing_status": "none"}))
    nc.wait_for("tasks", "(title,like,Paste transcript%)")
    nc.wait_for("activities", "(type,eq,automation_error)")


def test_W6a_03_accepted_b2b_routes_to_dorota(nc, hook):
    lid = make_lead(nc, type="B2B", contact_name="Firma X")
    mid = make_meeting(nc, lid)
    nc.create("tasks", {"title": "Verify AI analysis: Discovery — Test",
                        "status": "todo", "description": f"meeting:{mid}"})
    row = {"Id": mid, "title": "Discovery — Test",
           "processing_status": "ai_accepted", "owner": OWNER}
    hook("w6a-meeting-ai", nc_update(row, {**row, "processing_status": "ai_draft_ready"}))
    goals = nc.wait_for("tasks", "(title,like,Define training goals%)")
    assert (goals[0].get("assignee") or {}).get("email", "").startswith("dorota")
    assert nc.get("leads", lid)["offer_prep_status"] == "waiting_goals"
    verify = nc.list("tasks", "(title,like,Verify AI%)")
    assert verify[0]["status"] == "done"                     # W6a-07 partial


def test_W6a_06_unchanged_status_is_noop(nc, hook):
    lid = make_lead(nc)
    mid = make_meeting(nc, lid, processing_status="ai_draft_ready")
    row = {"Id": mid, "processing_status": "ai_draft_ready", "notes": "edit",
           "owner": OWNER}
    hook("w6a-meeting-ai", nc_update(row, {**row, "notes": "old"}))
    nc.wait_quiet("tasks", "(created_by_flow,eq,W6a)")


# ================================================================ W6b
def test_W6b_01_goals_provided_chains_testimonials(nc, hook):
    lid = make_lead(nc, contact_name="Klient Y")
    nc.create("tasks", {"title": "Define training goals: Klient Y", "status": "todo",
                        "description": f"lead:{lid}"})
    row = {"Id": lid, "contact_name": "Klient Y", "offer_prep_status": "goals_provided"}
    hook("w6b-offer-pipeline", nc_update(row, {**row, "offer_prep_status": "waiting_goals"}))
    nc.wait_for("tasks", "(title,like,Select testimonials%)")
    assert nc.list("tasks", "(title,like,Define training goals%)")[0]["status"] == "done"


def test_W6b_02_testimonials_linked_completes(nc, hook):
    lid = make_lead(nc, contact_name="Klient Z")
    tid = nc.create("testimonials", {"title": "Ref 1", "active": True})
    nc.link("leads", "selected_testimonials", lid, tid)
    row = {"Id": lid, "contact_name": "Klient Z",
           "offer_prep_status": "testimonials_provided"}
    hook("w6b-offer-pipeline", nc_update(row, {**row, "offer_prep_status": "goals_provided"}))
    nc.wait_for("tasks", "(title,like,Offer draft ready%)")
    assert nc.get("leads", lid)["offer_prep_status"] == "draft_ready"


def test_W6b_03_no_testimonials_blocks(nc, hook):
    lid = make_lead(nc, contact_name="Klient Q")
    row = {"Id": lid, "contact_name": "Klient Q",
           "offer_prep_status": "testimonials_provided"}
    hook("w6b-offer-pipeline", nc_update(row, {**row, "offer_prep_status": "goals_provided"}))
    nc.wait_for("activities", "(type,eq,automation_error)")
    assert nc.get("leads", lid)["offer_prep_status"] != "draft_ready"
    nc.wait_quiet("tasks", "(title,like,Offer draft ready%)")


def test_W6b_04_unchanged_status_is_noop(nc, hook):
    lid = make_lead(nc)
    row = {"Id": lid, "offer_prep_status": "none", "notes": "e"}
    hook("w6b-offer-pipeline", nc_update(row, {**row, "notes": "o"}))
    nc.wait_quiet("activities", "(flow,eq,W6b)")
