#!/usr/bin/env python3
r"""Generuje flow n8n schematu v4 do docs/archive/fable/*.json, z ID pól linków
odczytanymi z docs/archive/fable/schema_map.json (wynik `make dump-crm-schema`).

Dlaczego generator, a nie ręcznie pisane JSON-y: flow wołają API linków NocoDB
(`/links/{id pola}/records/{id rekordu}`), więc potrzebują ID pól relacji z
żywej instancji. Po każdym `make dump-crm-schema` wystarczy uruchomić ten skrypt
ponownie. ID TABEL flow biorą z node'a "Get one base" (konwencja
`.claude/skills/n8n-flow`), nie z generatora.

Etap 1 (docs/archive/fable/nocodb_crm_migration_v4.md):
  W15_resolve_assignee   podflow: rola / pracownik -> odpowiedzialny z regułą
                         zastępstw (employees + absences)
  W3_task_notifications  powiadomienie e-mail o zadaniu (webhook + podflow)
  W14_convert_lead       przycisk "Utwórz szansę sprzedaży" na leadzie
  W2_stage_change        zmiana etapu szansy: historia, kamienie milowe, zadania
  W16_scheduled_tasks    codziennie: scheduled -> todo + powiadomienie
  W0_recurring_tasks     zadania cykliczne z task_templates

Placeholdery do podmiany PO wygenerowaniu (sed, patrz README):
  __NOCODB_BASE_URL__   adres NocoDB widoczny z n8n (np. http://nocodb:8080)
  __W15_WORKFLOW_ID__   id zaimportowanego W15 (z adresu w n8n)
  __W3_WORKFLOW_ID__    id zaimportowanego W3

Usage:
  python3 scripts/gen-flows-v4.py              # zapisuje pliki
  python3 scripts/gen-flows-v4.py --check      # tylko walidacja grafu, bez zapisu
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FABLE = ROOT / "docs" / "archive" / "fable"
SM = json.load(open(FABLE / "schema_map.json"))

CRED = {"nocoDbApiToken": {"id": "9gq205HbXOk9D3Jm", "name": "NocoDB Token account"}}
SMTP = {"smtp": {"id": None, "name": "SMTP"}}
FROM_EMAIL = "info@coaction-test.pl"


def fid(table, field):
    try:
        return SM[table]["fields"][field]["id"]
    except KeyError:
        sys.exit(f"Brak pola {table}.{field} w schema_map.json: "
                 f"uruchom `make dump-crm-schema` po `make init-schema`.")


def ids_of_base():
    for t in SM.values():
        for f in t["fields"].values():
            raw = f.get("_raw_colOptions") or {}
            if raw.get("fk_workspace_id") and raw.get("base_id"):
                return raw["fk_workspace_id"], raw["base_id"]
    sys.exit("Nie znalazłem id workspace/bazy w schema_map.json.")


WORKSPACE_ID, BASE_ID = ids_of_base()
WS = "={{ $('Get one base').first().json.workspace_id }}"
PJ = "={{ $('Get one base').first().json.id }}"


def T(title):
    return ("={{ $('Get one base').first().json.tables.find(t => t.title === '%s').id }}"
            % title)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


class Flow:
    def __init__(self, name):
        self.name = name
        self.nodes = []
        self.conn = {}

    def add(self, name, typ, ver, params, col, row, creds=None, **extra):
        assert all(n["name"] != name for n in self.nodes), f"duplikat noda: {name}"
        n = {"parameters": params, "id": slug(name), "name": name, "type": typ,
             "typeVersion": ver, "position": [col * 260, row * 190]}
        if creds:
            n["credentials"] = creds
        n.update(extra)
        self.nodes.append(n)
        return name

    def to(self, a, b, out=0):
        main = self.conn.setdefault(a, {"main": []})["main"]
        while len(main) <= out:
            main.append([])
        main[out].append({"node": b, "type": "main", "index": 0})

    def chain(self, *names):
        for a, b in zip(names, names[1:]):
            self.to(a, b)

    def check(self):
        names = {n["name"] for n in self.nodes}
        for a, outs in self.conn.items():
            assert a in names, f"{self.name}: połączenie z nieistniejącego {a}"
            for lst in outs["main"]:
                for c in lst:
                    assert c["node"] in names, f"{self.name}: {a} -> brak {c['node']}"
        def strings(o):
            if isinstance(o, str):
                yield o
            elif isinstance(o, dict):
                for v in o.values():
                    yield from strings(v)
            elif isinstance(o, list):
                for v in o:
                    yield from strings(v)
        for n in self.nodes:
            for st in strings(n["parameters"]):
                if st.startswith("="):   # tylko wyrazenia n8n
                    assert st.count("{{") == st.count("}}"), (
                        f"{self.name}/{n['name']}: niezbalansowane wyrazenie: {st[:80]}")

    def doc(self):
        return {"name": self.name, "nodes": self.nodes, "connections": self.conn,
                "pinData": {}, "settings": {"executionOrder": "v1"}, "active": False,
                "meta": {"templateCredsSetupCompleted": False}}


# ------------------------------------------------------------------ builders
def webhook(f, name, path, col, row, response="onReceived"):
    return f.add(name, "n8n-nodes-base.webhook", 2,
                 {"httpMethod": "POST", "path": path, "responseMode": response,
                  "options": {}}, col, row, webhookId="wh-" + slug(path))


def base(f, col, row):
    return f.add("Get one base", "n8n-nodes-base.nocoDb", 4,
                 {"authentication": "nocoDbApiToken", "resource": "base",
                  "operation": "get",
                  "workspaceId": {"__rl": True, "value": WORKSPACE_ID, "mode": "list",
                                  "cachedResultName": "CoAction Workspace"},
                  "projectId": {"__rl": True, "value": BASE_ID, "mode": "list",
                                "cachedResultName": "CRM Base"}},
                 col, row, creds=CRED)


def code(f, name, js, col, row, mode=None):
    p = {"jsCode": js}
    if mode:
        p["mode"] = mode
    return f.add(name, "n8n-nodes-base.code", 2, p, col, row)


def if_(f, name, expr, col, row):
    return f.add(name, "n8n-nodes-base.if", 2.2,
                 {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                             "typeValidation": "loose"},
                                 "combinator": "and",
                                 "conditions": [{"id": "c1", "leftValue": expr,
                                                 "rightValue": "",
                                                 "operator": {"type": "boolean",
                                                              "operation": "true",
                                                              "singleValue": True}}]},
                  "options": {}}, col, row)


def nc(f, name, op, table, col, row, id=None, fields=None, where=None, limit=None,
       return_all=False, always_output=False, on_error=None):
    p = {"authentication": "nocoDbApiToken", "workspaceId": WS, "projectId": PJ,
         "table": T(table), "operation": op}
    if id is not None:
        p["id"] = id
    if op in ("create", "update"):
        p["dataToSend"] = "defineBelow"
    if fields:
        p["fieldsUi"] = {"fieldValues": [{"fieldName": k, "fieldValue": v}
                                         for k, v in fields.items()]}
    if op == "getAll":
        p["returnAll"] = return_all
        if not return_all:
            p["limit"] = limit or 50
        p["options"] = {"where": where} if where else {}
    extra = {}
    if always_output:
        extra["alwaysOutputData"] = True
    if on_error:
        extra["onError"] = on_error
    return f.add(name, "n8n-nodes-base.nocoDb", 3, p, col, row, creds=CRED, **extra)


def http_links_get(f, name, table, field, record_expr, col, row):
    """GET powiązanych rekordów (pole relacji `table.field`) rekordu o id z record_expr."""
    url = ("=__NOCODB_BASE_URL__/api/v2/tables/{{ $('Get one base').first().json.tables"
           ".find(t => t.title === '%s').id }}/links/%s/records/{{ %s }}?limit=200"
           % (table, fid(table, field), record_expr))
    return f.add(name, "n8n-nodes-base.httpRequest", 4,
                 {"method": "GET", "url": url,
                  "authentication": "predefinedCredentialType",
                  "nodeCredentialType": "nocoDbApiToken", "options": {}},
                 col, row, creds=CRED)


def http_links_batch(f, name, col, row):
    """POST linków z elementów {table_id, field_id, record_id, body} (po jednym na element)."""
    url = ("=__NOCODB_BASE_URL__/api/v2/tables/{{ $json.table_id }}/links/"
           "{{ $json.field_id }}/records/{{ $json.record_id }}")
    return f.add(name, "n8n-nodes-base.httpRequest", 4,
                 {"method": "POST", "url": url,
                  "authentication": "predefinedCredentialType",
                  "nodeCredentialType": "nocoDbApiToken", "sendBody": True,
                  "specifyBody": "json", "jsonBody": "={{ $json.body }}",
                  "options": {}}, col, row, creds=CRED)


def http_patch(f, name, table, body_expr, col, row):
    url = ("=__NOCODB_BASE_URL__/api/v2/tables/{{ $('Get one base').first().json.tables"
           ".find(t => t.title === '%s').id }}/records" % table)
    return f.add(name, "n8n-nodes-base.httpRequest", 4,
                 {"method": "PATCH", "url": url,
                  "authentication": "predefinedCredentialType",
                  "nodeCredentialType": "nocoDbApiToken", "sendBody": True,
                  "specifyBody": "json", "jsonBody": "={{ JSON.stringify(%s) }}" % body_expr,
                  "options": {}}, col, row, creds=CRED)


def email(f, name, to_expr, subject_expr, text_expr, col, row):
    return f.add(name, "n8n-nodes-base.emailSend", 2.1,
                 {"fromEmail": FROM_EMAIL, "toEmail": to_expr, "subject": subject_expr,
                  "text": text_expr, "options": {}}, col, row, creds=SMTP)


def call(f, name, wf_placeholder, col, row):
    return f.add(name, "n8n-nodes-base.executeWorkflow", 1.1,
                 {"source": "database",
                  "workflowId": {"__rl": True, "value": wf_placeholder, "mode": "id"},
                  "mode": "each", "options": {"waitForSubWorkflow": True}}, col, row)


def merge(f, name, n_inputs, col, row):
    return f.add(name, "n8n-nodes-base.merge", 3, {"numberInputs": n_inputs}, col, row)


def field_map_js(pairs):
    """Literał JS {'tabela.pole': 'id'} dla kodu tworzącego batch linków."""
    return json.dumps({f"{t}.{fld}": fid(t, fld) for t, fld in pairs}, indent=1)


LINK_HELPER = '''
const TBL = t => $('Get one base').first().json.tables.find(x => x.title === t).id;
const link = (table, field, recordId, targetIds) => {
  const ids = (Array.isArray(targetIds) ? targetIds : [targetIds]).filter(Boolean);
  if (!recordId || !ids.length) return null;
  return { json: { table_id: TBL(table), field_id: FIELD[table + '.' + field],
                   record_id: recordId, body: JSON.stringify(ids.map(Id => ({ Id }))) } };
};
'''


# ================================================================== W15
def build_w15():
    f = Flow("W15 - Resolve assignee (role -> employee, absences)")
    t = f.add("Resolve assignee: input", "n8n-nodes-base.executeWorkflowTrigger", 1.1,
              {"inputSource": "passthrough"}, 0, 2)
    b = base(f, 1, 2)
    norm = code(f, "Normalize request", """
// Wejscie: preferred_employee_id (opcjonalne), role, on_date (YYYY-MM-DD).
const i = $input.first().json;
const today = new Date().toISOString().slice(0, 10);
return [{ json: {
  preferred_employee_id: i.preferred_employee_id || null,
  role: i.role || 'handlowiec',
  on_date: String(i.on_date || today).slice(0, 10),
} }];
""", 2, 2)
    has_pref = if_(f, "Preferred employee given?", "={{ !!$json.preferred_employee_id }}", 3, 2)
    get_pref = nc(f, "Get preferred employee", "get", "employees", 4, 1,
                  id="={{ $json.preferred_employee_id }}", always_output=True)
    get_role = nc(f, "Get active employees with role", "getAll", "employees", 4, 3,
                  where="=(role,eq,{{ $json.role }})~and(is_active,eq,true)", limit=20,
                  always_output=True)
    pick = code(f, "Pick candidate", """
const req = $('Normalize request').first().json;
const rows = $input.all().map(i => i.json).filter(e => e && e.Id && e.is_active !== false);
rows.sort((a, b) => a.Id - b.Id);
const c = rows[0] || null;
return [{ json: { ...req, candidate: c ? { id: c.Id, email: c.email, name: c.full_name } : null } }];
""", 5, 2)
    found = if_(f, "Candidate found?", "={{ !!$json.candidate }}", 6, 2)
    get_abs = http_links_get(f, "Get candidate absences", "employees", "absences",
                             "$json.candidate.id", 7, 1)
    absent = code(f, "Is candidate absent?", """
const ctx = $('Pick candidate').first().json;
const list = $input.first().json.list || [];
const d = ctx.on_date;
const a = list.find(x => x.start_date && x.end_date && x.start_date <= d && d <= x.end_date);
return [{ json: { ...ctx, absent: !!a, absence_id: a ? a.Id : null } }];
""", 8, 1)
    is_abs = if_(f, "Candidate absent?", "={{ $json.absent }}", 9, 1)
    res_c = code(f, "Result: the candidate", """
const c = $input.first().json.candidate;
return [{ json: { assignee_id: c.id, assignee_email: c.email, assignee_name: c.name,
                  reason: 'candidate' } }];
""", 10, 0)
    get_sub = http_links_get(f, "Get substitutes of the absence", "absences", "substitutes",
                             "$json.absence_id", 10, 2)
    lst = code(f, "List substitutes", """
const ctx = $('Is candidate absent?').first().json;
const list = ($input.first().json.list || []).filter(e => e.is_active !== false);
if (!list.length) return [{ json: { ...ctx, has_any: false } }];
return list.map(e => ({ json: { ...ctx, has_any: true,
  substitute: { id: e.Id, email: e.email, name: e.full_name } } }));
""", 11, 2)
    any_sub = if_(f, "Any substitute?", "={{ $json.has_any }}", 12, 2)
    get_sub_abs = http_links_get(f, "Get substitute absences", "employees", "absences",
                                 "$json.substitute.id", 13, 1)
    free = code(f, "Pick first free substitute", """
const subs = $('List substitutes').all();
const res = $input.all();
for (let i = 0; i < subs.length; i++) {
  const s = subs[i].json, d = s.on_date;
  const list = (res[i] && res[i].json && res[i].json.list) || [];
  const busy = list.some(a => a.start_date && a.end_date && a.start_date <= d && d <= a.end_date);
  if (!busy) {
    return [{ json: { assignee_id: s.substitute.id, assignee_email: s.substitute.email,
      assignee_name: s.substitute.name, reason: 'substitute for ' + s.candidate.name } }];
  }
}
return [{ json: { need_admin: true } }];
""", 14, 1)
    got_free = if_(f, "Free substitute found?", "={{ !$json.need_admin }}", 15, 1)
    admin = nc(f, "Get admin employees", "getAll", "employees", 16, 4,
               where="=(role,eq,admin)~and(is_active,eq,true)", limit=20, always_output=True)
    res_a = code(f, "Result: admin fallback", """
const rows = $input.all().map(i => i.json).filter(e => e && e.Id);
rows.sort((a, b) => a.Id - b.Id);
const a = rows[0];
if (!a) return [{ json: { assignee_id: null, assignee_email: null, assignee_name: null,
                          reason: 'no available employee' } }];
return [{ json: { assignee_id: a.Id, assignee_email: a.email, assignee_name: a.full_name,
                  reason: 'admin fallback' } }];
""", 17, 4)
    ret = code(f, "Return assignee", "return $input.all();", 18, 2)

    f.chain(t, b, norm, has_pref)
    f.to(has_pref, get_pref, 0)
    f.to(has_pref, get_role, 1)
    f.to(get_pref, pick)
    f.to(get_role, pick)
    f.chain(pick, found)
    f.to(found, get_abs, 0)
    f.to(found, admin, 1)
    f.chain(get_abs, absent, is_abs)
    f.to(is_abs, get_sub, 0)
    f.to(is_abs, res_c, 1)
    f.chain(get_sub, lst, any_sub)
    f.to(any_sub, get_sub_abs, 0)
    f.to(any_sub, admin, 1)
    f.chain(get_sub_abs, free, got_free)
    f.to(got_free, ret, 0)
    f.to(got_free, admin, 1)
    f.chain(admin, res_a, ret)
    f.to(res_c, ret)
    return f


# ================================================================== W3
def build_w3():
    f = Flow("W3 - Task notifications (webhook + subflow)")
    wh = webhook(f, "NocoDB: tasks insert/update", "w3-task-notify", 0, 1)
    sub = f.add("Notify about task: input", "n8n-nodes-base.executeWorkflowTrigger", 1.1,
                {"inputSource": "passthrough"}, 0, 3)
    norm = code(f, "Normalize input", """
// Dwa wejscia: webhook tabeli tasks (reczne zmiany w UI) albo podflow (task_id).
const j = $input.first().json;
if (j.task_id) return [{ json: { task_id: j.task_id } }];
const b = j.body || j;
const t = b.type || '';
const row = (b.data && b.data.rows && b.data.rows[0]) || {};
const prev = (b.data && b.data.previous_rows && b.data.previous_rows[0]) || {};
const id = o => (o && (o.Id || (Array.isArray(o) && o[0] && o[0].Id))) || null;
if (!row.Id) return [];
if (t.includes('update')) {
  // Aktualizacje powiadamiamy tylko, gdy da sie stwierdzic zmiane odpowiedzialnego.
  const cur = id(row.assignee), old = id(prev.assignee);
  if (!cur || cur === old) return [];
}
return [{ json: { task_id: row.Id } }];
""", 1, 2)
    b = base(f, 2, 2)
    get_task = nc(f, "Get task", "get", "tasks", 3, 1, id="={{ $('Normalize input').first().json.task_id }}")
    get_asg = http_links_get(f, "Get task assignee", "tasks", "assignee",
                             "$('Normalize input').first().json.task_id", 3, 3)
    mg = merge(f, "Wait for task and assignee", 2, 4, 2)
    comp = code(f, "Compose notification", """
const task = $('Get task').first().json;
const a = (($('Get task assignee').first().json.list) || [])[0];
if (!a || !a.email) return [];
return [{ json: {
  to: a.email,
  subject: `Nowe zadanie: ${task.title}`,
  text: `Masz zadanie w CRM:\\n\\n${task.title}\\nTermin: ${task.due_date || '-'}\\n` +
        `Zaplanowane na: ${task.scheduled_for || '-'}\\nPriorytet: ${task.priority || 'normal'}\\n\\n` +
        `Szczegóły w NocoDB.`,
  summary: `Powiadomienie wysłane do ${a.email}: ${task.title}`,
  task_id: task.Id,
} }];
""", 5, 2)
    send = email(f, "Send task notification", "={{ $json.to }}", "={{ $json.subject }}",
                 "={{ $json.text }}", 6, 2)
    log = nc(f, "Log activity: notification sent", "create", "activities", 7, 2, fields={
        "summary": "={{ $('Compose notification').first().json.summary }}",
        "type": "notification_sent", "flow": "W3", "triggered_by": "system",
        "payload": "={{ JSON.stringify({ task_id: $('Compose notification').first().json.task_id }) }}"})
    f.to(wh, norm)
    f.to(sub, norm)
    f.chain(norm, b)
    f.to(b, get_task)
    f.to(b, get_asg)
    f.to(get_task, mg, 0)
    f.to(get_asg, mg, 1)
    f.chain(mg, comp, send, log)
    return f


# ================================================================== W14
def build_w14():
    f = Flow("W14 - Convert lead to sale opportunity (button)")
    FIELD = field_map_js([("persons", "bought_opportunities"), ("leads", "opportunities"),
                          ("employees", "opportunities"), ("companies", "opportunities"),
                          ("sale_opportunities", "history"),
                          ("sale_opportunities", "activities"), ("leads", "activities")])
    wh = webhook(f, "Button: Utwórz szansę sprzedaży", "w14-convert-lead", 0, 2)
    b = base(f, 1, 2)
    guard = code(f, "Guard", """
// Przycisk NocoDB (payload v3) wysyla caly wiersz leada razem z polami relacji:
// primary_person / owner / company jako {Id, ...} albo null, opportunities jako tablica.
const body = $input.first().json.body || $input.first().json;
const row = (body.data && body.data.rows && body.data.rows[0]) || body;
const idOf = o => (o && (o.Id || (Array.isArray(o) && o[0] && o[0].Id))) || null;
const existing = Array.isArray(row.opportunities) ? row.opportunities.length
               : (Number(row.opportunities) || 0);
let error = null;
if (!idOf(row.primary_person)) error = 'Brak głównego kontaktu (primary_person) na leadzie.';
else if (existing) error = 'Szansa dla tego leada już istnieje (nie tworzę drugiej).';
return [{ json: {
  ok: !error, error_message: error, lead_id: row.Id,
  lead_name: row.lead_name || ('lead #' + row.Id),
  segment: row.lead_type === 'B2B' ? 'B2B' : 'B2C',
  primary_person_id: idOf(row.primary_person), owner_id: idOf(row.owner),
  company_id: idOf(row.company),
} }];
""", 2, 2)
    mark = nc(f, "Set convert status: generating", "update", "leads", 3, 2,
              id="={{ $json.lead_id }}",
              fields={"convert_status": "generating", "convert_note": ""})
    passed = if_(f, "Passed checks on the lead?",
                 "={{ $('Guard').first().json.ok }}", 4, 2)
    person = nc(f, "Get primary person", "get", "persons", 5, 1,
                id="={{ $('Guard').first().json.primary_person_id }}")
    val = code(f, "Validate conversion", """
// Jedyny odczyt spoza payloadu: tryb sprzedazy osoby (sales_mode) nie jest w
// payloadzie przycisku, a pelny rekord osoby tak.
const g = $('Guard').first().json;
const p = $input.first().json;
const error = p.sales_mode === 'Tylko spotkania'
  ? 'Główny kontakt ma tryb "Tylko spotkania" - nie tworzymy dla niego szansy.' : null;
return [{ json: { ...g, ok: !error, error_message: error, person_id: p.Id || g.primary_person_id } }];
""", 6, 1)
    valid = if_(f, "Conversion allowed?", "={{ $json.ok }}", 7, 1)
    # Dwie sciezki bledu: kontrola z payloadu (komunikat w Guard) i kontrola
    # sales_mode (komunikat w Validate conversion); id leada zawsze z Guard.
    err = nc(f, "Write conversion error", "update", "leads", 8, 4,
             id="={{ $('Guard').first().json.lead_id }}",
             fields={"convert_status": "error",
                     "convert_note": "={{ $json.error_message || $('Guard').first().json.error_message }}"})
    err_act = nc(f, "Log activity: conversion refused", "create", "activities", 9, 4, fields={
        "summary": "={{ 'Konwersja leada odrzucona: ' + $json.convert_note }}",
        "type": "automation_error", "flow": "W14", "triggered_by": "user",
        "payload": "={{ JSON.stringify({ lead_id: $json.Id }) }}"})
    create = nc(f, "Create sale opportunity", "create", "sale_opportunities", 8, 0, fields={
        "name": "={{ $json.lead_name }}", "segment": "={{ $json.segment }}",
        "stage": "Nowa", "state": "open", "label": "Nowy klient",
        "stage_changed_at": "={{ $now.toISO() }}"}, on_error="continueErrorOutput")
    hist = nc(f, "Create first stage history row", "create",
              "sale_opportunity_stage_history", 9, 0, fields={
                  "title": "Utworzono: Nowa", "to_stage": "Nowa",
                  "changed_at": "={{ $now.toISO() }}", "changed_by": "n8n:W14"})
    act = nc(f, "Log activity: opportunity created", "create", "activities", 10, 0, fields={
        "summary": "={{ 'Utworzono szansę sprzedaży z leada: ' + $('Validate conversion').first().json.lead_name }}",
        "type": "stage_changed", "flow": "W14", "triggered_by": "user",
        "payload": "={{ JSON.stringify({ lead_id: $('Validate conversion').first().json.lead_id, opportunity_id: $('Create sale opportunity').first().json.Id }) }}"})
    prep = code(f, "Prepare links", "const FIELD = " + FIELD + ";\n" + LINK_HELPER + """
const v = $('Validate conversion').first().json;
const opp = $('Create sale opportunity').first().json.Id;
const hist = $('Create first stage history row').first().json.Id;
const act = $('Log activity: opportunity created').first().json.Id;
return [
  link('persons', 'bought_opportunities', v.person_id, opp),
  link('leads', 'opportunities', v.lead_id, opp),
  link('employees', 'opportunities', v.owner_id, opp),
  link('companies', 'opportunities', v.company_id, opp),
  link('sale_opportunities', 'history', opp, hist),
  link('sale_opportunities', 'activities', opp, act),
  link('leads', 'activities', v.lead_id, act),
].filter(Boolean);
""", 11, 0)
    links = http_links_batch(f, "Link records to the new opportunity", 12, 0)
    done = nc(f, "Set convert status: done", "update", "leads", 13, 0,
              id="={{ $('Validate conversion').first().json.lead_id }}",
              fields={"convert_status": "done", "convert_note": ""})
    unexpected = code(f, "Prepare unexpected error", """
const v = $('Validate conversion').first().json;
const e = $input.first().json;
return [{ json: { lead_id: v.lead_id, error_message:
  'Nie udało się utworzyć szansy: ' + ((e.error && (e.error.message || e.error)) || 'nieznany błąd') } }];
""", 9, 2)
    f.chain(wh, b, guard, mark, passed)
    f.to(passed, person, 0)
    f.to(passed, err, 1)
    f.chain(person, val, valid)
    f.to(valid, create, 0)
    f.to(valid, err, 1)
    f.chain(err, err_act)
    f.to(create, hist, 0)
    f.to(create, unexpected, 1)
    f.to(unexpected, err)
    f.chain(hist, act, prep, links, done)
    return f


# ================================================================== W2
def build_w2():
    f = Flow("W2 - Sale opportunity stage change (milestones, history, tasks)")
    FIELD = field_map_js([("sale_opportunities", "history"),
                          ("sale_opportunities", "activities"),
                          ("sale_opportunities", "tasks"), ("employees", "tasks"),
                          ("persons", "tasks")])
    wh = webhook(f, "NocoDB: sale_opportunities updated", "w2-stage-change", 0, 2)
    b = base(f, 1, 2)
    guard = code(f, "Guard & prepare", """
// NocoDB odpala webhook przy KAZDEJ aktualizacji - dzialamy tylko, gdy realnie
// zmienil sie etap. Wymaga "send me previous record" na webhooku tabeli.
const body = $input.first().json.body || $input.first().json;
const row = (body.data && body.data.rows && body.data.rows[0]) || {};
const prev = (body.data && body.data.previous_rows && body.data.previous_rows[0]) || {};
const s = row.stage, p = prev.stage;
if (!s || s === p) return [];

const today = new Date().toISOString().slice(0, 10);
const patch = { Id: row.Id, stage_changed_at: new Date().toISOString() };
if (s === 'Oferta wysłana')   patch.offer_sent_at = today;
if (s === 'Umowa wysłana')    patch.contract_sent_at = today;
if (s === 'Umowa podpisana')  { patch.state = 'won';      patch.closed_at = today; }
if (s === 'Utracona')         { patch.state = 'lost';     patch.closed_at = today; }
if (s === 'Zarchiwizowana')   { patch.state = 'archived'; patch.closed_at = today; }

// Zadania przy przejsciach (docs/archive/fable/nocodb_crm_schema_v4.md, "Zasady
// tworzenia zadan"). Przejscie na "Audyt" dojdzie w etapie 3.
const tasks = [];
if (s === 'Rekomendacja / demo')
  tasks.push({ task_type: 'prepare_offer', role: 'handlowiec', use_owner: true,
               title: `Przygotuj ofertę: ${row.name}`, due_in_days: 1 });
if (s === 'Umowa podpisana')
  tasks.push({ task_type: 'invoice', role: 'finanse', use_owner: false,
               title: `Wystaw fakturę: ${row.name}`, due_in_days: 3 });

const idOf = o => (o && (o.Id || (Array.isArray(o) && o[0] && o[0].Id))) || null;
const owner_id = idOf(row.owner), buyer_id = idOf(row.person);
tasks.forEach(t => { t.preferred_employee_id = t.use_owner ? owner_id : null; });

return [{ json: { opp_id: row.Id, opp_name: row.name || ('szansa #' + row.Id),
  old_stage: p || '(brak)', new_stage: s, patch, tasks, owner_id, buyer_id } }];
""", 2, 2)
    has_owner_id = if_(f, "Owner set on the opportunity?",
                       "={{ !!$('Guard & prepare').first().json.owner_id }}", 3, 2)
    get_owner = nc(f, "Get owner employee", "get", "employees", 4, 1,
                   id="={{ $('Guard & prepare').first().json.owner_id }}")
    asm = code(f, "Assemble transition", """
const g = $('Guard & prepare').first().json;
let owner = null;
try { owner = $('Get owner employee').first().json; } catch (e) { owner = null; }
return [{ json: { ...g, owner_email: owner && owner.email ? owner.email : null } }];
""", 5, 2)
    # --- gałąź A: kamienie milowe
    upd = http_patch(f, "Update opportunity milestones (variable field set)",
                     "sale_opportunities", "[$('Assemble transition').first().json.patch]", 6, 0)
    # --- gałąź B: historia, aktywność, mail do właściciela
    hist = nc(f, "Create stage history row", "create", "sale_opportunity_stage_history", 6, 2,
              fields={
                  "title": "={{ $('Assemble transition').first().json.old_stage + ' → ' + $('Assemble transition').first().json.new_stage }}",
                  "from_stage": "={{ $('Assemble transition').first().json.old_stage === '(brak)' ? '' : $('Assemble transition').first().json.old_stage }}",
                  "to_stage": "={{ $('Assemble transition').first().json.new_stage }}",
                  "changed_at": "={{ $now.toISO() }}", "changed_by": "n8n:W2"})
    act = nc(f, "Log activity: stage changed", "create", "activities", 7, 2, fields={
        "summary": "={{ $('Assemble transition').first().json.opp_name + ': ' + $('Assemble transition').first().json.old_stage + ' → ' + $('Assemble transition').first().json.new_stage }}",
        "type": "stage_changed", "flow": "W2", "triggered_by": "system",
        "payload": "={{ JSON.stringify({ opportunity_id: $('Assemble transition').first().json.opp_id }) }}"})
    prep = code(f, "Prepare links for history and activity",
                "const FIELD = " + FIELD + ";\n" + LINK_HELPER + """
const a = $('Assemble transition').first().json;
return [
  link('sale_opportunities', 'history', a.opp_id, $('Create stage history row').first().json.Id),
  link('sale_opportunities', 'activities', a.opp_id, $('Log activity: stage changed').first().json.Id),
].filter(Boolean);
""", 8, 2)
    links = http_links_batch(f, "Link history and activity to the opportunity", 9, 2)
    has_owner = if_(f, "Owner has an email?",
                    "={{ !!$('Assemble transition').first().json.owner_email }}", 10, 2)
    mail = email(f, "Notify owner about the stage change",
                 "={{ $('Assemble transition').first().json.owner_email }}",
                 "={{ 'CRM: ' + $('Assemble transition').first().json.opp_name + ' → ' + $('Assemble transition').first().json.new_stage }}",
                 "={{ 'Szansa ' + $('Assemble transition').first().json.opp_name + ' przeszła z etapu ' + $('Assemble transition').first().json.old_stage + ' na ' + $('Assemble transition').first().json.new_stage + '.' }}",
                 11, 2)
    # --- gałąź C: zadania
    build = code(f, "Build transition tasks", """
const a = $('Assemble transition').first().json;
const today = new Date();
const addDays = n => new Date(today.getTime() + n * 86400000).toISOString().slice(0, 10);
return (a.tasks || []).map(t => ({ json: { ...t,
  preferred_employee_id: t.preferred_employee_id || null,
  due_date: addDays(t.due_in_days), on_date: addDays(t.due_in_days) } }));
""", 6, 4)
    resolve = call(f, "Resolve who should do the task", "__W15_WORKFLOW_ID__", 7, 4)
    attach = code(f, "Attach task details to the assignee", """
const src = $('Build transition tasks').all();
const res = $input.all();
return res.map((r, i) => ({ json: { ...src[i].json, ...r.json } }));
""", 8, 4)
    create = nc(f, "Create task", "create", "tasks", 9, 4, fields={
        "title": "={{ $json.title }}", "task_type": "={{ $json.task_type }}",
        "status": "todo", "priority": "normal", "due_date": "={{ $json.due_date }}",
        "created_by_flow": "W2"})
    prep_t = code(f, "Prepare task links", "const FIELD = " + FIELD + ";\n" + LINK_HELPER + """
const a = $('Assemble transition').first().json;
const att = $('Attach task details to the assignee').all();
const created = $input.all();
const out = [];
created.forEach((c, i) => {
  const tid = c.json.Id, asg = att[i].json.assignee_id;
  out.push(link('employees', 'tasks', asg, tid));
  out.push(link('sale_opportunities', 'tasks', a.opp_id, tid));
  out.push(link('persons', 'tasks', a.buyer_id, tid));
});
return out.filter(Boolean);
""", 10, 4)
    links_t = http_links_batch(f, "Link task to assignee, opportunity and buyer", 11, 4)
    notify = code(f, "Collect created task ids", """
const created = $('Create task').all();
return created.map(c => ({ json: { task_id: c.json.Id } }));
""", 12, 4, mode="runOnceForAllItems")
    send = call(f, "Notify assignee about the task", "__W3_WORKFLOW_ID__", 13, 4)

    f.chain(wh, b, guard)
    f.to(guard, has_owner_id)
    f.to(has_owner_id, get_owner, 0)
    f.to(has_owner_id, asm, 1)
    f.to(get_owner, asm)
    f.to(asm, upd)
    f.to(asm, hist)
    f.to(asm, build)
    f.chain(hist, act, prep, links, has_owner)
    f.to(has_owner, mail, 0)
    f.chain(build, resolve, attach, create, prep_t, links_t, notify, send)
    return f


# ================================================================== W16
def build_w16():
    f = Flow("W16 - Scheduled tasks become due (scheduled -> todo + notification)")
    cron = f.add("Every day 07:00", "n8n-nodes-base.scheduleTrigger", 1.2,
                 {"rule": {"interval": [{"field": "cronExpression",
                                         "expression": "0 7 * * *"}]}}, 0, 1)
    b = base(f, 1, 1)
    due = nc(f, "Get scheduled tasks that are due", "getAll", "tasks", 2, 1,
             where="=(status,eq,scheduled)~and(scheduled_for,le,{{ $now.toFormat('yyyy-MM-dd') }})",
             return_all=True)
    flip = nc(f, "Set task status to todo", "update", "tasks", 3, 1,
              id="={{ $json.Id }}", fields={"status": "todo"})
    get_asg = http_links_get(f, "Get task assignee", "tasks", "assignee", "$json.Id", 4, 1)
    prep = code(f, "Prepare reminder", """
const tasks = $('Get scheduled tasks that are due').all();
const res = $input.all();
const today = new Date().toISOString().slice(0, 10);
const out = [];
res.forEach((r, i) => {
  const t = tasks[i].json;
  const a = ((r.json.list) || [])[0];
  if (!a) return;   // zadanie bez odpowiedzialnego: tylko zmiana statusu
  out.push({ json: { task_id: t.Id, title: t.title, scheduled_for: t.scheduled_for,
                     preferred_employee_id: a.Id, original_name: a.full_name,
                     original_email: a.email, on_date: today } });
});
return out;
""", 5, 1)
    resolve = call(f, "Resolve who should be reminded (absences)", "__W15_WORKFLOW_ID__", 6, 1)
    compose = code(f, "Compose reminder", """
const src = $('Prepare reminder').all();
const res = $input.all();
return res.map((r, i) => {
  const s = src[i].json, a = r.json;
  const to = a.assignee_email || s.original_email;
  const sub = a.assignee_id && a.assignee_name !== s.original_name
    ? ` (zastępstwo za ${s.original_name})` : '';
  return { json: { to, task_id: s.task_id,
    subject: `Zadanie na dziś: ${s.title}`,
    text: `Zadanie zaplanowane na ${s.scheduled_for} jest już do zrobienia${sub}:\\n\\n${s.title}\\n\\nSzczegóły w NocoDB.`,
    summary: `Przypomnienie o zadaniu wysłane do ${to}: ${s.title}` } };
});
""", 7, 1)
    send = email(f, "Send due-task reminder", "={{ $json.to }}", "={{ $json.subject }}",
                 "={{ $json.text }}", 8, 1)
    log = nc(f, "Log activity: reminder sent", "create", "activities", 9, 1, fields={
        "summary": "={{ $('Compose reminder').item.json.summary }}",
        "type": "notification_sent", "flow": "W16", "triggered_by": "system",
        "payload": "={{ JSON.stringify({ task_id: $('Compose reminder').item.json.task_id }) }}"})
    f.chain(cron, b, due, flip, get_asg, prep, resolve, compose, send, log)
    return f


# ================================================================== W0
def build_w0():
    f = Flow("W0 - Recurring tasks (from task_templates)")
    FIELD = field_map_js([("employees", "tasks")])
    cron = f.add("Every day 06:00", "n8n-nodes-base.scheduleTrigger", 1.2,
                 {"rule": {"interval": [{"field": "cronExpression",
                                         "expression": "0 6 * * *"}]}}, 0, 1)
    b = base(f, 1, 1)
    tmpl = nc(f, "Get active templates", "getAll", "task_templates", 2, 1,
              where="=(active,eq,true)", return_all=True)
    t_asg = http_links_get(f, "Get template assignee", "task_templates", "assignee",
                           "$json.Id", 3, 1)
    attach = code(f, "Attach assignees to templates", """
const t = $('Get active templates').all();
const r = $input.all();
return [{ json: { templates: t.map((x, i) => ({ ...x.json,
  assignee_id: ((r[i].json.list || [])[0] || {}).Id || null })) } }];
""", 4, 1)
    existing = nc(f, "Get already created recurring tasks", "getAll", "tasks", 5, 1,
                  where="=(created_by_flow,eq,W0)~and(due_date,ge,{{ $now.toFormat('yyyy-MM-dd') }})",
                  return_all=True, always_output=True)
    parse = code(f, "Parse & dedupe", """
// Ktore szablony sa dzis na rzedzie (podzbior RRULE: DAILY/WEEKLY/MONTHLY).
const templates = $('Attach assignees to templates').first().json.templates || [];
const existing = $input.all().map(i => i.json).filter(r => r && r.Id)
  .map(r => (r.title || '') + '|' + (r.due_date || ''));
const now = new Date();
const dow = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'][now.getDay()];
const dom = now.getDate();
const month = now.toISOString().slice(0, 7);
const iso = d => d.toISOString().slice(0, 10);
function dueToday(rrule) {
  if (!rrule) return false;
  const p = Object.fromEntries(rrule.split(';').map(s => s.split('=')));
  const freq = (p.FREQ || '').toUpperCase();
  if (freq === 'DAILY') return true;
  if (freq === 'WEEKLY') return (p.BYDAY || '').split(',').includes(dow);
  if (freq === 'MONTHLY') return parseInt(p.BYMONTHDAY || '1', 10) === dom;
  return false;
}
const out = [];
for (const t of templates) {
  if (!dueToday(t.rrule)) continue;
  const due = new Date(now.getTime() + (t.due_offset_days || 0) * 86400000);
  const title = (t.title || 'Zadanie').replaceAll('{{month}}', month);
  if (existing.includes(title + '|' + iso(due))) continue;   // idempotencja
  out.push({ json: { template_id: t.Id, assignee_id: t.assignee_id, title,
    description: t.description || '', due_date: iso(due) } });
}
return out;
""", 6, 1)
    create = nc(f, "Create recurring task", "create", "tasks", 7, 1, fields={
        "title": "={{ $json.title }}", "task_type": "other", "status": "todo",
        "priority": "normal", "description": "={{ $json.description }}",
        "due_date": "={{ $json.due_date }}", "created_by_flow": "W0"})
    prep = code(f, "Prepare assignee links", "const FIELD = " + FIELD + ";\n" + LINK_HELPER + """
const src = $('Parse & dedupe').all();
return $input.all().map((c, i) => link('employees', 'tasks', src[i].json.assignee_id, c.json.Id))
  .filter(Boolean);
""", 8, 1)
    links = http_links_batch(f, "Link task to its assignee", 9, 1)
    ids = code(f, "Collect created task ids", """
return $('Create recurring task').all().map(c => ({ json: { task_id: c.json.Id } }));
""", 10, 1, mode="runOnceForAllItems")
    notify = call(f, "Notify assignee about the task", "__W3_WORKFLOW_ID__", 11, 1)
    f.chain(cron, b, tmpl, t_asg, attach, existing, parse, create, prep, links, ids, notify)
    return f


FLOWS = {
    "W15_resolve_assignee.json": build_w15,
    "W3_task_notifications.json": build_w3,
    "W14_convert_lead.json": build_w14,
    "W2_stage_change.json": build_w2,
    "W16_scheduled_tasks.json": build_w16,
    "W0_recurring_tasks.json": build_w0,
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="tylko walidacja grafu")
    args = ap.parse_args()
    for fname, builder in FLOWS.items():
        flow = builder()
        flow.check()
        print(f"ok  {fname}: {len(flow.nodes)} node'ów")
        if not args.check:
            (FABLE / fname).write_text(
                json.dumps(flow.doc(), ensure_ascii=False, indent=2) + "\n")
    if not args.check:
        print("Zapisano do docs/archive/fable/. Podmień placeholdery (README).")
