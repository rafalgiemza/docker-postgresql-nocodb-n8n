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


class MissingField(Exception):
    pass


ALLOW_MISSING = False   # --check: brakujace pola zastepuje placeholderem


def have(table, field):
    return table in SM and field in SM[table]["fields"]


def fid(table, field):
    if have(table, field):
        return SM[table]["fields"][field]["id"]
    if ALLOW_MISSING:
        return f"__FIELD_{table}_{field}__"
    raise MissingField(f"{table}.{field}")


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

    def to_ai(self, a, b, kind="ai_languageModel"):
        self.conn.setdefault(a, {}).setdefault(kind, [[]])[0].append(
            {"node": b, "type": kind, "index": 0})

    def chain(self, *names):
        for a, b in zip(names, names[1:]):
            self.to(a, b)

    def check(self):
        names = {n["name"] for n in self.nodes}
        for a, outs in self.conn.items():
            assert a in names, f"{self.name}: połączenie z nieistniejącego {a}"
            for kind, groups in outs.items():
                for lst in groups:
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
                          ("persons", "tasks"), ("sale_opportunities", "to_be_audited"),
                          ("sale_opportunities", "participants")])
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
if (s === 'Umowa podpisana') {
  tasks.push({ task_type: 'invoice', role: 'finanse', use_owner: false,
               title: `Wystaw fakturę: ${row.name}`, due_in_days: 3 });
  tasks.push({ task_type: 'take_over_participants', role: 'metodyczka', use_methodologist: true,
               title: `Przejmij uczestników: ${row.name}`, due_in_days: 2 });
}
// W B2C kupujacy jest sam uczestnikiem i sam jedyna osoba do audytu.
if (s === 'Audyt' && row.segment === 'B2C')
  tasks.push({ task_type: 'audit_prep', role: 'metodyczka', use_methodologist: true,
               title: `Przygotowanie audytu: ${(row.person && row.person.full_name) || row.name}`,
               due_in_days: 2 });

const idOf = o => (o && (o.Id || (Array.isArray(o) && o[0] && o[0].Id))) || null;
const owner_id = idOf(row.owner), buyer_id = idOf(row.person);
const segment = row.segment || null;
const participants_count = Array.isArray(row.participants) ? row.participants.length : 0;

return [{ json: { opp_id: row.Id, opp_name: row.name || ('szansa #' + row.Id),
  old_stage: p || '(brak)', new_stage: s, patch, tasks, owner_id, buyer_id,
  segment, participants_count } }];
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
    g_meth = http_links_get(f, "Get methodologist of the buyer", "persons",
                            "assigned_methodologist",
                            "$('Assemble transition').first().json.buyer_id || 0", 6, 5)
    for n_ in f.nodes:
        if n_["name"] == g_meth:
            n_["onError"] = "continueRegularOutput"
            n_["alwaysOutputData"] = True
    build = code(f, "Build transition tasks", """
const a = $('Assemble transition').first().json;
let meth = null;
try { meth = ((($('Get methodologist of the buyer').first().json) || {}).list || [])[0] || null; }
catch (e) { meth = null; }
const today = new Date();
const addDays = n => new Date(today.getTime() + n * 86400000).toISOString().slice(0, 10);
return (a.tasks || []).map(t => ({ json: { ...t,
  preferred_employee_id: t.use_owner ? a.owner_id
                       : (t.use_methodologist && meth ? meth.Id : null),
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
if (a.new_stage === 'Audyt' && a.segment === 'B2C')
  out.push(link('sale_opportunities', 'to_be_audited', a.opp_id, a.buyer_id));
if (a.new_stage === 'Umowa podpisana' && a.segment === 'B2C' && !a.participants_count)
  out.push(link('sale_opportunities', 'participants', a.opp_id, a.buyer_id));
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
    f.to(asm, g_meth)
    f.chain(hist, act, prep, links, has_owner)
    f.to(has_owner, mail, 0)
    f.chain(g_meth, build, resolve, attach, create, prep_t, links_t, notify, send)
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


# ================================================================== AI helpers
OPENROUTER = {"openRouterApi": {"id": "sd2Yv1RgXeRJ2gk9", "name": "OpenRouter account"}}


def ai_agent(f, name, system_message, text_expr, col, row, model_name="OpenRouter Chat Model"):
    """AI Agent + sub-node modelu (zasady: .ai/rules/ai-n8n.md §3). Prompt
    metodyczny siedzi w System Message, nie w kodzie."""
    a = f.add(name, "@n8n/n8n-nodes-langchain.agent", 1.9,
              {"promptType": "define", "text": text_expr,
               "options": {"systemMessage": system_message}}, col, row,
              onError="continueErrorOutput")
    m = f.add(model_name, "@n8n/n8n-nodes-langchain.lmChatOpenRouter", 1,
              {"model": "anthropic/claude-sonnet-4.5", "options": {"timeout": 60000}},
              col, row + 1, creds=OPENROUTER)
    f.to_ai(m, a)
    return a


# ================================================================== W6a
MEETING_SYSTEM_MESSAGE = """Jesteś asystentem szkoły językowej CoAction (angielski dla IT i biznesu). Analizujesz transkrypcję i notatki ze spotkania discovery z klientem i wyciągasz z nich dane do oferty.

Zasady:
- Opieraj się WYŁĄCZNIE na transkrypcji i notatkach. Niczego nie dopisuj od siebie; jeśli czegoś nie ma w rozmowie, wpisz "brak danych w rozmowie".
- Pisz po polsku, konkretnie, językiem biznesowym, bez ogólników. Teksty trafiają na slajdy oferty, więc pisz je tak, żeby klient mógł je przeczytać.
- Zwróć WYŁĄCZNIE obiekt JSON (bez komentarza i bez bloku kodu) z dokładnie takimi kluczami:
  "goals": cele klienta wobec szkolenia,
  "challenges": wyzwania i problemy zgłaszane podczas spotkania,
  "participant_types": jacy ludzie i jakie role będą uczestniczyć w szkoleniu (skrót, nie lista imion),
  "business_context": kontekst biznesowy firmy lub klienta wynikający z rozmowy,
  "communication_situations": konkretne sytuacje komunikacyjne po angielsku, w których klient bierze udział (np. negocjacje z dostawcą, prezentacje dla zarządu); to one zasilają audyt językowy."""


def build_w6a():
    f = Flow("W6a - Meeting analysis (button: Generuj analizę)")
    need = [("meetings", "tasks"), ("meetings", "activities"), ("employees", "tasks"),
            ("sale_opportunities", "activities")]
    FIELD = field_map_js(need)
    wh = webhook(f, "Button: Generuj analizę", "w6a-meeting-analysis", 0, 3)
    b = base(f, 1, 3)
    pending = nc(f, "Set ai_status: pending", "update", "meetings", 2, 3,
                 id="={{ $('Button: Generuj analizę').first().json.body.data.rows[0].Id }}",
                 fields={"ai_status": "pending"})
    guard = code(f, "Guard", """
// Przycisk NocoDB (payload v3) wysyla wiersz spotkania razem z relacjami.
const body = $('Button: Generuj analizę').first().json.body || $('Button: Generuj analizę').first().json;
const row = (body.data && body.data.rows && body.data.rows[0]) || body;
const idOf = o => (o && (o.Id || (Array.isArray(o) && o[0] && o[0].Id))) || null;
const names = a => Array.isArray(a) ? a.map(x => x.full_name || x.title).filter(Boolean) : [];
const transcript = String(row.transcript || '').trim();
const notes = String(row.notes || '').trim();
return [{ json: { meeting_id: row.Id, title: row.title || ('spotkanie #' + row.Id),
  meeting_type: row.meeting_type || '', starts_at: row.starts_at || '',
  attendees: names(row.attendees), transcript, notes,
  owner_id: idOf(row.owner), opp_id: idOf(row.sale_opportunity),
  enough: transcript.length >= 50 } }];
""", 3, 3)
    enough = if_(f, "Transcript long enough?", "={{ $json.enough }}", 4, 3)
    # --- brak danych: ai_rejected + jedno zadanie provide_input
    reject = nc(f, "Reject: transcript missing", "update", "meetings", 5, 5,
                id="={{ $('Guard').first().json.meeting_id }}",
                fields={"ai_status": "ai_rejected",
                        "ai_analysis_raw": "Brak transkrypcji (min. 50 znaków). Wklej transkrypcję w pole transcript i kliknij „Generuj analizę” ponownie."})
    g_tasks = http_links_get(f, "Get tasks linked to the meeting", "meetings", "tasks",
                             "$('Guard').first().json.meeting_id", 6, 5)
    open_t = code(f, "Is the input task still missing?", """
const list = $input.first().json.list || [];
const open = list.some(t => t.task_type === 'provide_input' && t.status !== 'done' && t.status !== 'cancelled');
const g = $('Guard').first().json;
return open ? [] : [{ json: { title: `Wklej transkrypcję: ${g.title}`, due: new Date().toISOString().slice(0, 10) } }];
""", 7, 5)
    task = nc(f, "Task: paste the transcript", "create", "tasks", 8, 5, fields={
        "title": "={{ $json.title }}", "task_type": "provide_input", "status": "todo",
        "priority": "high", "due_date": "={{ $json.due }}", "created_by_flow": "W6a"})
    t_prep = code(f, "Prepare task links", "const FIELD = " + FIELD + ";\n" + LINK_HELPER + """
const g = $('Guard').first().json;
const tid = $input.first().json.Id;
return [link('employees', 'tasks', g.owner_id, tid), link('meetings', 'tasks', g.meeting_id, tid)].filter(Boolean);
""", 9, 5)
    t_links = http_links_batch(f, "Link the task to the owner and the meeting", 10, 5)
    # --- analiza AI
    ctx = code(f, "Assemble context", """
const g = $('Guard').first().json;
const text = [
  `Spotkanie: ${g.title}`,
  g.meeting_type ? `Typ: ${g.meeting_type}` : '',
  g.starts_at ? `Data: ${g.starts_at}` : '',
  g.attendees.length ? `Uczestnicy: ${g.attendees.join(', ')}` : '',
  g.notes ? `\\nNOTATKI:\\n${g.notes}` : '',
  `\\nTRANSKRYPCJA:\\n${g.transcript}`,
].filter(Boolean).join('\\n');
return [{ json: { user: text } }];
""", 5, 1)
    agent = ai_agent(f, "AI Agent", MEETING_SYSTEM_MESSAGE, "={{ $json.user }}", 6, 1)
    parse = code(f, "Parse AI output", """
const KEYS = ['goals', 'challenges', 'participant_types', 'business_context', 'communication_situations'];
const raw = String(($input.first().json.output || $input.first().json.text || '')).trim();
const m = raw.match(/\\{[\\s\\S]*\\}/);
let obj = null;
try { obj = m ? JSON.parse(m[0]) : null; } catch (e) { obj = null; }
if (!obj || KEYS.some(k => typeof obj[k] !== 'string')) {
  return [{ json: { ok: false, error_message: 'Model zwrócił odpowiedź w nieoczekiwanym formacie.', raw } }];
}
return [{ json: { ok: true, raw, ...Object.fromEntries(KEYS.map(k => [k, obj[k]])) } }];
""", 7, 1)
    ok = if_(f, "AI output valid?", "={{ $json.ok }}", 8, 1)
    save = nc(f, "Save analysis (draft)", "update", "meetings", 9, 0,
              id="={{ $('Guard').first().json.meeting_id }}", fields={
                  "goals": "={{ $json.goals }}", "challenges": "={{ $json.challenges }}",
                  "participant_types": "={{ $json.participant_types }}",
                  "business_context": "={{ $json.business_context }}",
                  "communication_situations": "={{ $json.communication_situations }}",
                  "ai_analysis_raw": "={{ $json.raw }}", "ai_status": "ai_draft_ready"})
    act = nc(f, "Log activity: AI analysis ready", "create", "activities", 10, 0, fields={
        "summary": "={{ 'Analiza AI spotkania gotowa do weryfikacji: ' + $('Guard').first().json.title }}",
        "type": "ai_analysis_done", "flow": "W6a", "triggered_by": "user",
        "payload": "={{ JSON.stringify({ meeting_id: $('Guard').first().json.meeting_id }) }}"})
    a_prep = code(f, "Prepare activity links", "const FIELD = " + FIELD + ";\n" + LINK_HELPER + """
const g = $('Guard').first().json;
const aid = $input.first().json.Id;
return [link('meetings', 'activities', g.meeting_id, aid),
        link('sale_opportunities', 'activities', g.opp_id, aid)].filter(Boolean);
""", 11, 0)
    a_links = http_links_batch(f, "Link the activity to the meeting and the opportunity", 12, 0)
    # --- błąd AI: reset statusu + komunikat w polu, bez zadania
    err_prep = code(f, "Prepare AI error", """
const e = $input.first().json;
const msg = e.error_message || (e.error && (e.error.message || String(e.error))) || 'nieznany błąd';
return [{ json: { message: 'Analiza AI nie powiodła się (' + msg + '). Kliknij „Generuj analizę” ponownie; jeśli błąd się powtarza, sprawdź transkrypcję.' } }];
""", 9, 2)
    err_save = nc(f, "Reset status and write the error", "update", "meetings", 10, 2,
                  id="={{ $('Guard').first().json.meeting_id }}",
                  fields={"ai_status": "none", "ai_analysis_raw": "={{ $json.message }}"})
    err_act = nc(f, "Log activity: AI analysis failed", "create", "activities", 11, 2, fields={
        "summary": "={{ 'Analiza AI spotkania nie powiodła się: ' + $('Guard').first().json.title }}",
        "type": "automation_error", "flow": "W6a", "triggered_by": "user",
        "payload": "={{ JSON.stringify({ meeting_id: $('Guard').first().json.meeting_id, error: $('Prepare AI error').first().json.message }) }}"})

    f.chain(wh, b, pending, guard, enough)
    f.to(enough, ctx, 0)
    f.to(enough, reject, 1)
    f.chain(reject, g_tasks, open_t, task, t_prep, t_links)
    f.chain(ctx, agent)
    f.to(agent, parse, 0)
    f.to(agent, err_prep, 1)
    f.chain(parse, ok)
    f.to(ok, save, 0)
    f.to(ok, err_prep, 1)
    f.chain(save, act, a_prep, a_links)
    f.chain(err_prep, err_save, err_act)
    return f


# ================================================================== W7
# Mapowanie rezerwacji cal.com -> meeting_type. Klucz: slug typu wydarzenia
# albo eventTypeId (deterministyczne atrybuty rezerwacji; tytul jest dla ludzi).
# Uzupelnij po utworzeniu typow wydarzen w cal.com (patrz plan migracji).
MEETING_TYPE_BY_SLUG = {"discovery": "discovery", "audyt": "audit", "audit": "audit",
                        "demo": "demo"}
MEETING_TYPE_BY_EVENT_TYPE_ID = {}   # np. {"123456": "discovery"}


def build_w7():
    f = Flow("W7 - cal.com bookings -> meetings (webhook)")
    for fld in (("meetings", "attendees"), ("meetings", "activities"),
                ("employees", "meetings"), ("sale_opportunities", "meetings"),
                ("sale_opportunities", "activities"), ("persons", "bought_opportunities")):
        fid(*fld)   # wczesny, czytelny błąd, gdy etap 2 nie jest zdumpowany
    lookups = [("bought_opportunities", fid("persons", "bought_opportunities"))]
    for extra in ("to_be_audited_in", "participant_in"):   # dochodzą w etapie 3
        if have("persons", extra):
            lookups.append((extra, fid("persons", extra)))
    FIELD = field_map_js([("meetings", "attendees"), ("meetings", "activities"),
                          ("employees", "meetings"), ("sale_opportunities", "meetings"),
                          ("sale_opportunities", "activities")])
    wh = webhook(f, "cal.com: booking event", "w7-calcom-booking", 0, 4)
    b = base(f, 1, 4)
    norm = code(f, "Normalize booking", """
// Webhook cal.com: { triggerEvent, payload: {...} }. Struktura niezweryfikowana na
// zywej instancji - kod toleruje drobne roznice nazw pol.
const b = $input.first().json.body || $input.first().json;
const kind = ({ BOOKING_CREATED: 'created', BOOKING_RESCHEDULED: 'rescheduled',
                BOOKING_CANCELLED: 'cancelled' })[b.triggerEvent];
if (!kind) return [];
const p = b.payload || b;
const TYPE_BY_SLUG = %s;
const TYPE_BY_ID = %s;
const slug = String(p.type || (p.eventType && p.eventType.slug) || '').toLowerCase();
const typeId = p.eventTypeId || (p.eventType && p.eventType.id) || null;
const meeting_type = TYPE_BY_ID[String(typeId)] || TYPE_BY_SLUG[slug] || null;
const attendees = (p.attendees || []).filter(a => a && a.email)
  .map(a => ({ email: String(a.email).trim().toLowerCase(), name: a.name || '' }));
return [{ json: { kind, uid: p.uid || null,
  previous_uid: p.rescheduleUid || p.rescheduledFromUid || null,
  title: p.title || p.eventTitle || 'Rezerwacja cal.com',
  starts_at: p.startTime || null, ends_at: p.endTime || null,
  organizer_email: String((p.organizer && p.organizer.email) || '').trim().toLowerCase(),
  attendees, meeting_type, event_slug: slug, event_type_id: typeId } }];
""" % (json.dumps(MEETING_TYPE_BY_SLUG), json.dumps(MEETING_TYPE_BY_EVENT_TYPE_ID)), 2, 4)
    route = f.add("Route by booking event", "n8n-nodes-base.switch", 3.2,
                  {"mode": "expression", "numberOutputs": 3,
                   "output": "={{ ['created','rescheduled','cancelled'].indexOf($json.kind) }}"},
                  3, 4)
    # ---------------- utworzenie
    exist = nc(f, "Find meeting by booking uid", "getAll", "meetings", 4, 0,
               where="=(external_id,eq,{{ $json.uid }})", limit=1, always_output=True)
    is_new = code(f, "Is it a new booking?", """
const n = $('Normalize booking').first().json;
const found = $input.all().some(i => i.json && i.json.Id);
return found || !n.uid ? [] : [{ json: n }];
""", 5, 0)
    split = code(f, "Split attendees", """
const n = $input.first().json;
return n.attendees.map(a => ({ json: { ...a } }));
""", 6, 0)
    find_p = nc(f, "Find person by email", "getAll", "persons", 7, 0,
                where="=(email,eq,{{ $json.email }})", limit=1, always_output=True)
    match = code(f, "Match person", """
const att = $('Split attendees').all();
return $input.all().map((r, i) => {
  const p = r.json && r.json.Id ? r.json : null;
  return { json: { ...att[i].json, person_id: p ? p.Id : null,
                   sales_mode: p ? (p.sales_mode || null) : null } };
});
""", 8, 0)
    person_ok = if_(f, "Person already exists?", "={{ !!$json.person_id }}", 9, 0)
    new_p = nc(f, "Create person from booking", "create", "persons", 10, 1, fields={
        "full_name": "={{ $json.name || $json.email }}", "email": "={{ $json.email }}"})
    new_p_tag = code(f, "Attach created person id", """
const src = $('Match person').all().filter(i => !i.json.person_id);
return $input.all().map((r, i) => ({ json: { ...src[i].json, person_id: r.json.Id } }));
""", 11, 1)
    mg_p = merge(f, "Join existing and new persons", 2, 12, 0)
    collect = code(f, "Collect attendees", """
const n = $('Is it a new booking?').first().json;
return [{ json: { ...n, people: $input.all().map(i => i.json) } }];
""", 13, 0)
    organizer = nc(f, "Find organizer employee", "getAll", "employees", 14, 0,
                   where="=(email,eq,{{ $json.organizer_email }})", limit=1, always_output=True)
    prep_m = code(f, "Prepare meeting record", """
const c = $('Collect attendees').first().json;
const emp = $input.first().json && $input.first().json.Id ? $input.first().json : null;
const record = { title: c.title, starts_at: c.starts_at, ends_at: c.ends_at,
                 status: 'scheduled', external_id: c.uid };
if (c.meeting_type) record.meeting_type = c.meeting_type;   // pole puste, gdy typ spoza mapowania
return [{ json: { record, owner_id: emp ? emp.Id : null,
                  person_ids: c.people.map(p => p.person_id).filter(Boolean),
                  title: c.title } }];
""", 15, 0)
    create_m = f.add("Create meeting (variable field set)", "n8n-nodes-base.httpRequest", 4,
                     {"method": "POST",
                      "url": ("=__NOCODB_BASE_URL__/api/v2/tables/{{ $('Get one base').first().json.tables"
                              ".find(t => t.title === 'meetings').id }}/records"),
                      "authentication": "predefinedCredentialType",
                      "nodeCredentialType": "nocoDbApiToken", "sendBody": True,
                      "specifyBody": "json",
                      "jsonBody": "={{ JSON.stringify($json.record) }}", "options": {}},
                     16, 0, creds=CRED)
    act = nc(f, "Log activity: meeting created", "create", "activities", 17, 0, fields={
        "summary": "={{ 'Spotkanie z rezerwacji cal.com: ' + $('Prepare meeting record').first().json.title }}",
        "type": "meeting_created", "flow": "W7", "triggered_by": "system",
        "payload": "={{ JSON.stringify({ meeting_id: $('Create meeting (variable field set)').first().json.Id }) }}"})
    link_prep = code(f, "Prepare links to owner and attendees",
                     "const FIELD = " + FIELD + ";\n" + LINK_HELPER + """
const m = $('Create meeting (variable field set)').first().json.Id;
const p = $('Prepare meeting record').first().json;
const a = $('Log activity: meeting created').first().json.Id;
return [link('employees', 'meetings', p.owner_id, m),
        link('meetings', 'attendees', m, p.person_ids),
        link('meetings', 'activities', m, a)].filter(Boolean);
""", 18, 0)
    links = http_links_batch(f, "Link the meeting to owner, attendees and activity", 19, 0)
    # ---------------- szansa sprzedaży (gałąź równoległa po utworzeniu spotkania)
    lk_items = code(f, "Build opportunity lookups", "const LOOKUPS = " + json.dumps(lookups) + ";\n" + """
// Dla osob w trybie "Tylko spotkania" nie szukamy szans (nigdy nie sa linkowane).
const c = $('Collect attendees').first().json;
const out = [];
for (const p of c.people) {
  if (!p.person_id || p.sales_mode === 'Tylko spotkania') continue;
  for (const [name, field_id] of LOOKUPS)
    out.push({ json: { person_id: p.person_id, field_id } });
}
return out;
""", 17, 3)
    lk_get = f.add("Get opportunities of the person", "n8n-nodes-base.httpRequest", 4,
                   {"method": "GET",
                    "url": ("=__NOCODB_BASE_URL__/api/v2/tables/{{ $('Get one base').first().json.tables"
                            ".find(t => t.title === 'persons').id }}/links/{{ $json.field_id }}"
                            "/records/{{ $json.person_id }}?limit=200"),
                    "authentication": "predefinedCredentialType",
                    "nodeCredentialType": "nocoDbApiToken", "options": {}},
                   18, 3, creds=CRED)
    pick = code(f, "Pick the only open opportunity", """
const open = new Map();
for (const r of $input.all())
  for (const o of (r.json.list || [])) if (o.state === 'open') open.set(o.Id, o);
if (open.size !== 1) return [];   // 0 lub wiele: spotkanie zostaje bez szansy
return [{ json: { opp_id: [...open.keys()][0] } }];
""", 19, 3)
    opp_prep = code(f, "Prepare opportunity links",
                    "const FIELD = " + FIELD + ";\n" + LINK_HELPER + """
const opp = $input.first().json.opp_id;
const m = $('Create meeting (variable field set)').first().json.Id;
const a = $('Log activity: meeting created').first().json.Id;
return [link('sale_opportunities', 'meetings', opp, m),
        link('sale_opportunities', 'activities', opp, a)].filter(Boolean);
""", 20, 3)
    opp_links = http_links_batch(f, "Link the meeting to the opportunity", 21, 3)
    # ---------------- przełożenie
    r_find = nc(f, "Find meeting of the previous booking", "getAll", "meetings", 4, 4,
                where="=(external_id,eq,{{ $json.previous_uid || $json.uid }})", limit=1,
                always_output=True)
    r_code = code(f, "Is the rescheduled meeting known?", """
const n = $('Normalize booking').first().json;
const m = $input.first().json;
return m && m.Id ? [{ json: { meeting_id: m.Id, ...n } }] : [];
""", 5, 4)
    r_upd = nc(f, "Move the meeting to the new time", "update", "meetings", 6, 4,
               id="={{ $json.meeting_id }}", fields={
                   "starts_at": "={{ $json.starts_at }}", "ends_at": "={{ $json.ends_at }}",
                   "external_id": "={{ $json.uid }}", "status": "scheduled"})
    # ---------------- anulowanie
    c_find = nc(f, "Find meeting of the cancelled booking", "getAll", "meetings", 4, 6,
                where="=(external_id,eq,{{ $json.uid }})", limit=1, always_output=True)
    c_code = code(f, "Is the cancelled meeting known?", """
const m = $input.first().json;
return m && m.Id ? [{ json: { meeting_id: m.Id } }] : [];
""", 5, 6)
    c_upd = nc(f, "Mark the meeting as cancelled", "update", "meetings", 6, 6,
               id="={{ $json.meeting_id }}", fields={"status": "cancelled"})

    f.chain(wh, b, norm, route)
    f.to(route, exist, 0)
    f.to(route, r_find, 1)
    f.to(route, c_find, 2)
    f.chain(exist, is_new, split, find_p, match, person_ok)
    f.to(person_ok, mg_p, 0)
    f.to(person_ok, new_p, 1)
    f.chain(new_p, new_p_tag)
    f.to(new_p_tag, mg_p, 1)
    f.chain(mg_p, collect, organizer, prep_m, create_m, act, link_prep, links)
    f.to(links, lk_items)   # szukanie szansy po zakonczeniu linkowania (aktywnosc juz istnieje)
    f.chain(lk_items, lk_get, pick, opp_prep, opp_links)
    f.chain(r_find, r_code, r_upd)
    f.chain(c_find, c_code, c_upd)
    return f


# ================================================================== W17
def http_links_dynamic(f, name, col, row):
    """Jak http_links_batch, ale metoda (POST dodaje, DELETE odlacza) z elementu."""
    url = ("=__NOCODB_BASE_URL__/api/v2/tables/{{ $json.table_id }}/links/"
           "{{ $json.field_id }}/records/{{ $json.record_id }}")
    return f.add(name, "n8n-nodes-base.httpRequest", 4,
                 {"method": "={{ $json.method || 'POST' }}", "url": url,
                  "authentication": "predefinedCredentialType",
                  "nodeCredentialType": "nocoDbApiToken", "sendBody": True,
                  "specifyBody": "json", "jsonBody": "={{ $json.body }}",
                  "options": {}}, col, row, creds=CRED)


def build_w17():
    f = Flow("W17 - Generate audit tasks (button on sale opportunity)")
    FIELD = field_map_js([("employees", "tasks"), ("persons", "tasks"),
                          ("sale_opportunities", "tasks"), ("meetings", "tasks")])
    BTN = "Button: Generuj zadania audytowe"
    wh = webhook(f, BTN, "w17-audit-tasks", 0, 3)
    b = base(f, 1, 3)
    mark = nc(f, "Set audit_tasks_status: generating", "update", "sale_opportunities", 2, 3,
              id="={{ $('%s').first().json.body.data.rows[0].Id }}" % BTN,
              fields={"audit_tasks_status": "generating", "audit_tasks_note": ""})
    guard = code(f, "Guard", """
const body = $('%s').first().json.body || $('%s').first().json;
const row = (body.data && body.data.rows && body.data.rows[0]) || body;
const persons = (Array.isArray(row.to_be_audited) ? row.to_be_audited : [])
  .map(p => ({ id: p.Id, name: p.full_name || p.title || ('osoba #' + p.Id) }));
const comp = row.company && (row.company.name || row.company.title);
return [{ json: { opp_id: row.Id, opp_name: row.name || ('szansa #' + row.Id),
                  company_name: comp || '', persons } }];
""" % (BTN, BTN), 3, 3)
    any_ = if_(f, "Anyone waiting for an audit?", "={{ $json.persons.length > 0 }}", 4, 3)
    empty1 = nc(f, "Set audit_tasks_status: done (empty list)", "update", "sale_opportunities", 5, 5,
                id="={{ $('Guard').first().json.opp_id }}",
                fields={"audit_tasks_status": "done",
                        "audit_tasks_note": "Lista „to_be_audited” jest pusta: nie ma dla kogo tworzyć zadań."})
    g_meet = http_links_get(f, "Get meetings of the opportunity", "sale_opportunities", "meetings",
                            "$('Guard').first().json.opp_id", 5, 2)
    split = code(f, "Split people and pick the discovery call", """
const g = $('Guard').first().json;
const meetings = ($input.first().json.list || [])
  .filter(m => m.meeting_type === 'discovery')
  .sort((a, b) => String(b.starts_at).localeCompare(String(a.starts_at)));
const meeting_id = meetings[0] ? meetings[0].Id : null;
return g.persons.map(p => ({ json: { person_id: p.id, person_name: p.name,
  opp_id: g.opp_id, opp_name: g.opp_name, company_name: g.company_name, meeting_id } }));
""", 6, 2)
    g_tasks = http_links_get(f, "Get tasks of the person", "persons", "tasks", "$json.person_id", 7, 2)
    skip = f.add("Skip people who already have an open audit task",
                 "n8n-nodes-base.code", 2, {"jsCode": """
const src = $('Split people and pick the discovery call').all();
const res = $input.all();
const out = [];
src.forEach((s, i) => {
  const list = (res[i] && res[i].json && res[i].json.list) || [];
  const open = list.some(t => t.task_type === 'audit_prep' && t.status !== 'done' && t.status !== 'cancelled');
  if (!open) out.push({ json: s.json });
});
return out;
"""}, 8, 2, alwaysOutputData=True)
    left = if_(f, "Anyone left to create a task for?", "={{ !!$json.person_id }}", 9, 2)
    empty2 = nc(f, "Set audit_tasks_status: done (all have tasks)", "update", "sale_opportunities", 10, 5,
                id="={{ $('Guard').first().json.opp_id }}",
                fields={"audit_tasks_status": "done",
                        "audit_tasks_note": "Każda osoba z listy ma już otwarte zadanie audytowe."})
    g_meth = http_links_get(f, "Get assigned methodologist of the person", "persons",
                            "assigned_methodologist", "$json.person_id", 10, 1)
    prefer = code(f, "Add preferred methodologist", """
const src = $('Skip people who already have an open audit task').all();
const res = $input.all();
const today = new Date();
const due = new Date(today.getTime() + 2 * 86400000).toISOString().slice(0, 10);
return src.map((s, i) => {
  const m = ((res[i] && res[i].json && res[i].json.list) || [])[0];
  return { json: { ...s.json, preferred_employee_id: m ? m.Id : null,
                   role: 'metodyczka', on_date: due, due_date: due } };
});
""", 11, 1)
    resolve = call(f, "Resolve who should prepare the audit", "__W15_WORKFLOW_ID__", 12, 1)
    attach = code(f, "Attach task details to the assignee", """
const src = $('Add preferred methodologist').all();
return $input.all().map((r, i) => ({ json: { ...src[i].json, ...r.json } }));
""", 13, 1)
    create = nc(f, "Create audit task", "create", "tasks", 14, 1, fields={
        "title": "={{ 'Przygotowanie audytu: ' + $json.person_name + ($json.company_name ? ' (' + $json.company_name + ')' : '') }}",
        "task_type": "audit_prep", "status": "todo", "priority": "normal",
        "due_date": "={{ $json.due_date }}", "created_by_flow": "W17"},
        on_error="continueErrorOutput")
    prep = code(f, "Prepare task links", "const FIELD = " + FIELD + ";\n" + LINK_HELPER + """
const att = $('Attach task details to the assignee').all();
const out = [];
$input.all().forEach((c, i) => {
  const a = att[i].json, tid = c.json.Id;
  out.push(link('employees', 'tasks', a.assignee_id, tid));
  out.push(link('persons', 'tasks', a.person_id, tid));
  out.push(link('sale_opportunities', 'tasks', a.opp_id, tid));
  out.push(link('meetings', 'tasks', a.meeting_id, tid));
});
return out.filter(Boolean);
""", 15, 1)
    links = http_links_batch(f, "Link tasks to assignee, person, opportunity and discovery call", 16, 1)
    collapse = code(f, "Count created tasks", """
const n = $('Create audit task').all().length;
return [{ json: { created: n } }];
""", 17, 0, mode="runOnceForAllItems")
    done = nc(f, "Set audit_tasks_status: done", "update", "sale_opportunities", 18, 0,
              id="={{ $('Guard').first().json.opp_id }}",
              fields={"audit_tasks_status": "done",
                      "audit_tasks_note": "={{ 'Utworzono zadań: ' + $json.created }}"})
    ids = code(f, "Collect created task ids", """
return $('Create audit task').all().map(c => ({ json: { task_id: c.json.Id } }));
""", 17, 2, mode="runOnceForAllItems")
    notify = call(f, "Notify assignee about the task", "__W3_WORKFLOW_ID__", 18, 2)
    err_prep = code(f, "Prepare audit tasks error", """
const e = $input.first().json;
const msg = (e.error && (e.error.message || String(e.error))) || 'nieznany błąd';
return [{ json: { message: 'Nie udało się utworzyć zadań audytowych (' + msg + '). Kliknij przycisk ponownie.' } }];
""", 15, 4)
    err_set = nc(f, "Set audit_tasks_status: error", "update", "sale_opportunities", 16, 4,
                 id="={{ $('Guard').first().json.opp_id }}",
                 fields={"audit_tasks_status": "error", "audit_tasks_note": "={{ $json.message }}"})
    err_act = nc(f, "Log activity: audit tasks failed", "create", "activities", 17, 4, fields={
        "summary": "={{ 'Nie udało się utworzyć zadań audytowych: ' + $('Guard').first().json.opp_name }}",
        "type": "automation_error", "flow": "W17", "triggered_by": "user",
        "payload": "={{ JSON.stringify({ opportunity_id: $('Guard').first().json.opp_id }) }}"})

    f.chain(wh, b, mark, guard, any_)
    f.to(any_, g_meet, 0)
    f.to(any_, empty1, 1)
    f.chain(g_meet, split, g_tasks, skip, left)
    f.to(left, g_meth, 0)
    f.to(left, empty2, 1)
    f.chain(g_meth, prefer, resolve, attach, create)
    f.to(create, prep, 0)
    f.to(create, err_prep, 1)
    f.chain(err_prep, err_set, err_act)
    f.chain(prep, links)
    f.to(links, collapse)
    f.to(links, ids)
    f.chain(collapse, done)
    f.chain(ids, notify)
    return f


# ================================================================== W18
def build_w18():
    f = Flow("W18 - Assessment saved -> person moves from to_be_audited to audited")
    FIELD = field_map_js([("sale_opportunities", "audited"),
                          ("sale_opportunities", "to_be_audited")])
    wh = webhook(f, "NocoDB: assessment saved", "w18-assessment-saved", 0, 2)
    b = base(f, 1, 2)
    guard = code(f, "Guard", """
// Webhook tabeli assessments (after insert ORAZ after update, ten sam URL):
// przy insercie linki moga jeszcze nie byc zapisane, wiec reagujemy tez na
// aktualizacje. Flow jest idempotentny (brak zmian = brak dzialania).
const body = $input.first().json.body || $input.first().json;
const row = (body.data && body.data.rows && body.data.rows[0]) || {};
const idOf = o => (o && (o.Id || (Array.isArray(o) && o[0] && o[0].Id))) || null;
const person_id = idOf(row.person), meeting_id = idOf(row.meeting);
if (!person_id || !meeting_id) return [];
return [{ json: { person_id, meeting_id } }];
""", 2, 2)
    g_opp = http_links_get(f, "Get opportunity of the audit meeting", "meetings", "sale_opportunity",
                           "$json.meeting_id", 3, 2)
    opp = code(f, "Opportunity id", """
const g = $('Guard').first().json;
const o = ($input.first().json.list || [])[0];
return o ? [{ json: { ...g, opp_id: o.Id } }] : [];
""", 4, 2)
    g_aud = http_links_get(f, "Get audited people", "sale_opportunities", "audited",
                           "$json.opp_id", 5, 1)
    g_tba = http_links_get(f, "Get people waiting for an audit", "sale_opportunities",
                           "to_be_audited", "$json.opp_id", 5, 3)
    mg = merge(f, "Wait for both lists", 2, 6, 2)
    decide = code(f, "Decide link changes", "const FIELD = " + FIELD + ";\n" + """
const TBL = t => $('Get one base').first().json.tables.find(x => x.title === t).id;
const o = $('Opportunity id').first().json;
const audited = ($('Get audited people').first().json.list || []).map(p => p.Id);
const waiting = ($('Get people waiting for an audit').first().json.list || []).map(p => p.Id);
const body = JSON.stringify([{ Id: o.person_id }]);
const out = [];
if (!audited.includes(o.person_id))
  out.push({ json: { method: 'POST', table_id: TBL('sale_opportunities'),
    field_id: FIELD['sale_opportunities.audited'], record_id: o.opp_id, body } });
if (waiting.includes(o.person_id))
  out.push({ json: { method: 'DELETE', table_id: TBL('sale_opportunities'),
    field_id: FIELD['sale_opportunities.to_be_audited'], record_id: o.opp_id, body } });
return out;
""", 7, 2)
    apply = http_links_dynamic(f, "Apply link change", 8, 2)
    f.chain(wh, b, guard, g_opp, opp)
    f.to(opp, g_aud)
    f.to(opp, g_tba)
    f.to(g_aud, mg, 0)
    f.to(g_tba, mg, 1)
    f.chain(mg, decide, apply)
    return f


# ================================================================== W19
def build_w19():
    f = Flow("W19 - Reminders for AI drafts waiting more than a day")
    FIELD = field_map_js([("employees", "tasks"), ("meetings", "tasks"),
                          ("assessments", "tasks"), ("recommendations", "tasks")])
    cron = f.add("Every day 08:00", "n8n-nodes-base.scheduleTrigger", 1.2,
                 {"rule": {"interval": [{"field": "cronExpression",
                                         "expression": "0 8 * * *"}]}}, 0, 3)
    b = base(f, 1, 3)
    branches = [("meetings", "meeting", "handlowiec", True),
                ("assessments", "assessment", "metodyczka", False),
                ("recommendations", "recommendation", "handlowiec", False)]
    for k, (table, label, role, owner_lookup) in enumerate(branches):
        r = k * 3          # wiersz gałęzi
        get = nc(f, f"Get {label} drafts", "getAll", table, 2, r,
                 where="=(ai_status,eq,ai_draft_ready)", return_all=True, always_output=True)
        stale = code(f, f"Keep {label} drafts waiting more than a day", """
const cutoff = Date.now() - 24 * 3600 * 1000;
return $input.all().filter(i => i.json && i.json.Id && i.json.UpdatedAt
  && new Date(i.json.UpdatedAt.replace(' ', 'T')).getTime() < cutoff)
  .map(i => ({ json: { record_id: i.json.Id, title: i.json.title || ('#' + i.json.Id) } }));
""", 3, r)
        g_t = http_links_get(f, f"Get tasks of the {label}", table, "tasks", "$json.record_id", 4, r)
        nodup = code(f, f"Skip {label} drafts that already have a reminder", """
const src = $('Keep %s drafts waiting more than a day').all();
const res = $input.all();
const today = new Date().toISOString().slice(0, 10);
const out = [];
src.forEach((s, i) => {
  const list = (res[i] && res[i].json && res[i].json.list) || [];
  const open = list.some(t => t.task_type === 'approve_ai_draft' && t.status !== 'done' && t.status !== 'cancelled');
  if (!open) out.push({ json: { ...s.json, role: '%s', on_date: today, due_date: today,
    task_title: 'Zatwierdź szkic AI (%s): ' + s.json.title } });
});
return out;
""" % (label, role, label), 5, r)
        prev_node = nodup
        if owner_lookup:
            g_o = http_links_get(f, f"Get owner of the {label}", table, "owner", "$json.record_id", 6, r)
            addo = code(f, f"Prefer the {label} owner", """
const src = $('Skip %s drafts that already have a reminder').all();
const res = $input.all();
return src.map((s, i) => ({ json: { ...s.json,
  preferred_employee_id: (((res[i] && res[i].json && res[i].json.list) || [])[0] || {}).Id || null } }));
""" % label, 7, r)
            f.chain(nodup, g_o, addo)
            prev_node = addo
        resolve = call(f, f"Resolve who should approve the {label} draft", "__W15_WORKFLOW_ID__", 8, r)
        attach = code(f, f"Attach {label} draft details to the assignee", """
const src = $('%s').all();
return $input.all().map((r, i) => ({ json: { ...src[i].json, ...r.json } }));
""" % (prev_node), 9, r)
        create = nc(f, f"Create {label} approval task", "create", "tasks", 10, r, fields={
            "title": "={{ $json.task_title }}", "task_type": "approve_ai_draft",
            "status": "todo", "priority": "normal", "due_date": "={{ $json.due_date }}",
            "created_by_flow": "W19"})
        prep = code(f, f"Prepare {label} task links", "const FIELD = " + FIELD + ";\n" + LINK_HELPER + """
const att = $('Attach %s draft details to the assignee').all();
const out = [];
$input.all().forEach((c, i) => {
  out.push(link('employees', 'tasks', att[i].json.assignee_id, c.json.Id));
  out.push(link('%s', 'tasks', att[i].json.record_id, c.json.Id));
});
return out.filter(Boolean);
""" % (label, table), 11, r)
        links = http_links_batch(f, f"Link the {label} approval task", 12, r)
        ids = code(f, f"Collect {label} task ids", """
return $('Create %s approval task').all().map(c => ({ json: { task_id: c.json.Id } }));
""" % label, 13, r, mode="runOnceForAllItems")
        notify = call(f, f"Notify assignee about the {label} approval task", "__W3_WORKFLOW_ID__", 14, r)
        f.to(b, get)
        f.chain(get, stale, g_t, nodup)
        f.chain(prev_node, resolve, attach, create, prep, links, ids, notify)
    f.to(cron, b)
    return f


# ================================================================== W8
def build_w8():
    f = Flow("W8 - Assessment needs summary (button: Generuj needs summary)")
    prompt = (ROOT / "scripts" / "flow-prompts" / "w8_needs_summary_system_message.txt").read_text()
    FIELD = field_map_js([("employees", "tasks"), ("assessments", "tasks"),
                          ("persons", "tasks"), ("sale_opportunities", "activities")])
    BTN = "Button: Generuj needs summary"
    wh = webhook(f, BTN, "w8-assessment-needs-summary", 0, 3)
    b = base(f, 1, 3)
    pending = nc(f, "Set ai_status: pending", "update", "assessments", 2, 3,
                 id="={{ $('%s').first().json.body.data.rows[0].Id }}" % BTN,
                 fields={"ai_status": "pending"})
    guard = code(f, "Guard", """
const body = $('%s').first().json.body || $('%s').first().json;
const row = (body.data && body.data.rows && body.data.rows[0]) || body;
const idOf = o => (o && (o.Id || (Array.isArray(o) && o[0] && o[0].Id))) || null;
return [{ json: { assessment_id: row.Id, person_id: idOf(row.person), meeting_id: idOf(row.meeting),
  title: row.title || ('ocena #' + row.Id),
  cefr_overall: row.cefr_overall || '', cefr_range: row.cefr_range || '',
  cefr_accuracy: row.cefr_accuracy || '', cefr_fluency: row.cefr_fluency || '',
  cefr_communication: row.cefr_communication || '', strengths: row.strengths || '',
  gaps: row.gaps || '', auditor_notes: row.auditor_notes || '',
  self_assessment: row.self_assessment || '', manager_needs: row.manager_needs || '',
  has_cefr: !!String(row.cefr_overall || '').trim() } }];
""" % (BTN, BTN), 3, 3)
    cefr = if_(f, "CEFR filled in?", "={{ $json.has_cefr }}", 4, 3)
    # --- brak ocen CEFR: ai_rejected + jedno zadanie provide_input
    rej = nc(f, "Reject: CEFR scores missing", "update", "assessments", 5, 6,
             id="={{ $('Guard').first().json.assessment_id }}",
             fields={"ai_status": "ai_rejected",
                     "needs_summary": "Brak ocen CEFR. Uzupełnij pola cefr_* w audycie i kliknij „Generuj needs summary” ponownie."})
    g_t = http_links_get(f, "Get tasks of the assessment", "assessments", "tasks",
                         "$('Guard').first().json.assessment_id", 6, 6)
    open_t = code(f, "Is the input task still missing?", """
const list = $input.first().json.list || [];
const open = list.some(t => t.task_type === 'provide_input' && t.status !== 'done' && t.status !== 'cancelled');
const g = $('Guard').first().json;
const due = new Date().toISOString().slice(0, 10);
return open ? [] : [{ json: { title: `Uzupełnij oceny CEFR: ${g.title}`, role: 'metodyczka',
  preferred_employee_id: null, on_date: due, due_date: due } }];
""", 7, 6)
    resolve_t = call(f, "Resolve who should fill in the scores", "__W15_WORKFLOW_ID__", 8, 6)
    attach_t = code(f, "Attach task details to the assignee", """
const src = $('Is the input task still missing?').all();
return $input.all().map((r, i) => ({ json: { ...src[i].json, ...r.json } }));
""", 9, 6)
    task = nc(f, "Task: fill in the CEFR scores", "create", "tasks", 10, 6, fields={
        "title": "={{ $json.title }}", "task_type": "provide_input", "status": "todo",
        "priority": "normal", "due_date": "={{ $json.due_date }}", "created_by_flow": "W8"})
    t_prep = code(f, "Prepare task links", "const FIELD = " + FIELD + ";\n" + LINK_HELPER + """
const g = $('Guard').first().json;
const a = $('Attach task details to the assignee').first().json;
const tid = $input.first().json.Id;
return [link('employees', 'tasks', a.assignee_id, tid), link('assessments', 'tasks', g.assessment_id, tid),
        link('persons', 'tasks', g.person_id, tid)].filter(Boolean);
""", 11, 6)
    t_links = http_links_batch(f, "Link the task to assignee, assessment and person", 12, 6)
    # --- odczyty kontekstu (równolegle)
    person = nc(f, "Get person", "get", "persons", 5, 1,
                id="={{ $('Guard').first().json.person_id }}", on_error="continueRegularOutput")
    g_comp = http_links_get(f, "Get company of the person", "persons", "company",
                            "$('Guard').first().json.person_id || 0", 5, 2)
    g_opp = http_links_get(f, "Get opportunity of the audit meeting", "meetings",
                           "sale_opportunity", "$('Guard').first().json.meeting_id || 0", 5, 3)
    opp_code = code(f, "Opportunity of the audit", """
const o = ($input.first().json.list || [])[0] || null;
return [{ json: { opp_id: o ? o.Id : null, segment: o ? (o.segment || '') : '' } }];
""", 6, 3)
    g_meet = http_links_get(f, "Get meetings of the opportunity", "sale_opportunities", "meetings",
                            "$json.opp_id || 0", 7, 3)
    for n_ in f.nodes:
        if n_["name"] in ("Get company of the person", "Get opportunity of the audit meeting",
                          "Get meetings of the opportunity"):
            n_["onError"] = "continueRegularOutput"
            n_["alwaysOutputData"] = True
    mg = merge(f, "Wait for person, company and discovery data", 3, 8, 2)
    ctx = code(f, "Assemble context", """
// Sklada dane z CRM w jeden tekst dla AI Agenta; prompt metodyczny siedzi w
// System Message noda "AI Agent" (edytowalny bez znajomosci JS).
const g = $('Guard').first().json;
const person = $('Get person').first().json || {};
let company = {};
try { company = (($('Get company of the person').first().json.list) || [])[0] || {}; } catch (e) {}
const opp = $('Opportunity of the audit').first().json;
let meetings = [];
try { meetings = ($('Get meetings of the opportunity').first().json.list) || []; } catch (e) {}
const latest = meetings.filter(m => m.meeting_type === 'discovery')
  .sort((a, b) => String(b.starts_at || '').localeCompare(String(a.starts_at || '')))[0] || {};
const accepted = latest.ai_status === 'ai_accepted';
const lines = [
  '## Wyniki audytu (ocena CEFR)',
  `Ogolny: ${g.cefr_overall || 'brak'}`,
  `Zakres jezyka: ${g.cefr_range || 'brak'}`,
  `Poprawnosc: ${g.cefr_accuracy || 'brak'}`,
  `Plynnosc: ${g.cefr_fluency || 'brak'}`,
  `Komunikatywnosc: ${g.cefr_communication || 'brak'}`,
  `Mocne strony: ${g.strengths || 'brak danych'}`,
  `Luki: ${g.gaps || 'brak danych'}`,
  '',
  '## Notatki metodyka po demo/audycie',
  g.auditor_notes || 'brak notatek',
  '',
  '## Kontekst uczestnika',
  `Imie i nazwisko: ${person.full_name || 'brak'}`,
  `Stanowisko: ${person.position || 'brak'}`,
  `Kontekst roli (z kim/o czym rozmawia po angielsku): ${person.role_context || 'brak'}`,
  `Czestotliwosc uzywania angielskiego: ${person.frequency || 'brak'}`,
  `Samoocena uczestnika: ${g.self_assessment || 'brak'}`,
  `Potrzeby wg managera/HR: ${g.manager_needs || 'brak'}`,
  '',
  '## Kontekst biznesowy',
  `Typ klienta: ${opp.segment || 'brak'}`,
  `Branza: ${person.industry || company.industry || 'brak'}`,
  company.name ? `Firma: ${company.name}` : null,
  company.communication_processes ? `Procesy komunikacyjne w firmie: ${company.communication_processes}` : null,
  company.business_impact ? `Wplyw jezyka na biznes: ${company.business_impact}` : null,
  '',
  '## Notatki z discovery call',
  latest.notes || 'brak notatek z discovery call (lub brak spotkania typu discovery dla tej szansy)',
  accepted && latest.goals ? `\\nCele klienta (zaakceptowana analiza): ${latest.goals}` : null,
  accepted && latest.challenges ? `Wyzwania (zaakceptowana analiza): ${latest.challenges}` : null,
  accepted && latest.communication_situations ? `Sytuacje komunikacyjne (zaakceptowana analiza): ${latest.communication_situations}` : null,
];
return [{ json: { user: lines.filter(l => l !== null).join('\\n'), opp_id: opp.opp_id } }];
""", 9, 2)
    agent = ai_agent(f, "AI Agent", prompt, "={{ $json.user }}", 10, 2)
    parse = code(f, "Parse AI output", """
const text = String(($input.first().json.output || '')).trim();
if (!text) return [{ json: { ok: false, error_message: 'Model zwrócił pustą odpowiedź.' } }];
return [{ json: { ok: true, text } }];
""", 11, 1)
    ok = if_(f, "AI output valid?", "={{ $json.ok }}", 12, 1)
    save = nc(f, "Save needs summary (draft)", "update", "assessments", 13, 0,
              id="={{ $('Guard').first().json.assessment_id }}",
              fields={"needs_summary": "={{ $json.text }}", "ai_status": "ai_draft_ready"})
    act = nc(f, "Log activity: AI needs summary ready", "create", "activities", 14, 0, fields={
        "summary": "={{ 'Szkic needs summary gotowy do weryfikacji: ' + $('Guard').first().json.title }}",
        "type": "ai_analysis_done", "flow": "W8", "triggered_by": "user",
        "payload": "={{ JSON.stringify({ assessment_id: $('Guard').first().json.assessment_id }) }}"})
    a_prep = code(f, "Prepare activity link", "const FIELD = " + FIELD + ";\n" + LINK_HELPER + """
const opp = $('Assemble context').first().json.opp_id;
return [link('sale_opportunities', 'activities', opp, $input.first().json.Id)].filter(Boolean);
""", 15, 0)
    a_links = http_links_batch(f, "Link the activity to the opportunity", 16, 0)
    err_prep = code(f, "Prepare AI error", """
const e = $input.first().json;
const msg = e.error_message || (e.error && (e.error.message || String(e.error))) || 'nieznany błąd';
return [{ json: { message: 'Generowanie needs summary nie powiodło się (' + msg + '). Kliknij „Generuj needs summary” ponownie.' } }];
""", 12, 3)
    err_save = nc(f, "Reset status and write the error", "update", "assessments", 13, 3,
                  id="={{ $('Guard').first().json.assessment_id }}",
                  fields={"ai_status": "none", "needs_summary": "={{ $json.message }}"})
    err_act = nc(f, "Log activity: AI needs summary failed", "create", "activities", 14, 3, fields={
        "summary": "={{ 'Generowanie needs summary nie powiodło się: ' + $('Guard').first().json.title }}",
        "type": "automation_error", "flow": "W8", "triggered_by": "user",
        "payload": "={{ JSON.stringify({ assessment_id: $('Guard').first().json.assessment_id, error: $('Prepare AI error').first().json.message }) }}"})

    f.chain(wh, b, pending, guard, cefr)
    f.to(cefr, person, 0)
    f.to(cefr, g_comp, 0)
    f.to(cefr, g_opp, 0)
    f.to(cefr, rej, 1)
    f.chain(g_opp, opp_code, g_meet)
    f.to(person, mg, 0)
    f.to(g_comp, mg, 1)
    f.to(g_meet, mg, 2)
    f.chain(mg, ctx, agent)
    f.to(agent, parse, 0)
    f.to(agent, err_prep, 1)
    f.chain(parse, ok)
    f.to(ok, save, 0)
    f.to(ok, err_prep, 1)
    f.chain(save, act, a_prep, a_links)
    f.chain(err_prep, err_save, err_act)
    f.chain(rej, g_t, open_t, resolve_t, attach_t, task, t_prep, t_links)
    return f


FLOWS = {
    "W15_resolve_assignee.json": build_w15,
    "W3_task_notifications.json": build_w3,
    "W14_convert_lead.json": build_w14,
    "W2_stage_change.json": build_w2,
    "W16_scheduled_tasks.json": build_w16,
    "W0_recurring_tasks.json": build_w0,
    "W6a_meeting_ai_pipeline.json": build_w6a,
    "W7_bookings_meetings_sync.json": build_w7,
    "W17_generate_audit_tasks.json": build_w17,
    "W18_assessment_saved.json": build_w18,
    "W19_ai_draft_reminders.json": build_w19,
    "W8_assessment_needs_summary.json": build_w8,
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="tylko walidacja grafu")
    args = ap.parse_args()
    ALLOW_MISSING = args.check
    for fname, builder in FLOWS.items():
        try:
            flow = builder()
        except MissingField as e:
            print(f"--  {fname}: pominięty, brak pola {e} w schema_map.json "
                  f"(zrób `make init-schema STAGE=N` i `make dump-crm-schema`)")
            continue
        flow.check()
        print(f"ok  {fname}: {len(flow.nodes)} node'ów")
        if not args.check:
            (FABLE / fname).write_text(
                json.dumps(flow.doc(), ensure_ascii=False, indent=2) + "\n")
    if not args.check:
        print("Zapisano do docs/archive/fable/. Podmień placeholdery (README).")
