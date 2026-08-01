#!/usr/bin/env python3
"""offer-service: renders PPTX offers from a NocoDB-stored template + data
assembled by the n8n workflow (W9) — this service does NOT talk to NocoDB
for reads anymore, only for the active template lookup and writing the
result back.

Flow (POST /generate {"lead_id": N, "data": {...}}):
  1. n8n (W9) has already fetched lead + participants (+ their assessment
     scores) + testimonials + company from NocoDB and shaped it into `data`
     — see the Template contract below for the exact shape it must have.
  2. fetch the ACTIVE template (offer_templates.file attachment, newest active)
  3. render: replace {{placeholders}} in all text frames and tables;
     duplicate slides marked in speaker notes with `repeat:participants`
     or `repeat:testimonials` (one copy per item, {{participant.*}} /
     {{testimonial.*}} context)
  4. upload the result to NocoDB storage, create an `offers` record
     (status=draft, data_json snapshot for history/regeneration), link it
     to the lead, return {offer_id, warnings}

Template contract (editable by non-developers in PowerPoint) — placeholders
resolve against whatever `data` n8n sends, e.g.:
  - {{lead.contact_name}}, {{lead.value}}, {{company.name}},
    {{offer.date}}, {{offer.variant}}, {{offer.participants_count}}
  - a slide with `repeat:participants` in its SPEAKER NOTES is duplicated
    once per entry in `data.participants`; use {{participant.full_name}},
    {{participant.position}}, {{participant.needs_summary}}, and — if that
    participant's dict has a nested "a" object (assessment scores) —
    {{participant.a.o}} {{participant.a.r}} {{participant.a.a}}
    {{participant.a.f}} {{participant.a.c}} (overall/range/accuracy/
    fluency/communication)
  - `repeat:testimonials` likewise, once per entry in `data.testimonials`;
    use {{testimonial.title}}, {{testimonial.content}}, {{testimonial.client_name}}
  - keep each {{placeholder}} inside ONE styling run (don't bold half of it),
    otherwise the paragraph's mixed formatting collapses to the first run's.

Env: NOCODB_URL, NOCODB_TOKEN, NOCODB_BASE_ID, PORT (default 8000)
"""
import json
import os
from datetime import date
from typing import Any

import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

NOCODB_URL = os.environ["NOCODB_URL"].rstrip("/")
TOKEN = os.environ["NOCODB_TOKEN"]
BASE_ID = os.environ["NOCODB_BASE_ID"]
TABLES = ["offer_templates", "offers"]
from renderer import render_pptx


# ------------------------------------------------------------- NocoDB client
# Same shape as fable/nocodb.py's NocoDB class (table/column ids resolved
# once, by title, against the live base) — kept inline here so this service
# has no dependency on the fable/ test-runner package. Only two tables now:
# reads (lead/participants/assessments/testimonials/company) all happen in
# n8n before this service is even called.
def api(method, path, **kw):
    r = requests.request(method, f"{NOCODB_URL}{path}",
                         headers={"xc-token": TOKEN}, timeout=30, **kw)
    if not r.ok:
        raise HTTPException(r.status_code, f"NocoDB {method} {path} -> {r.text[:400]}")
    return r.json() if r.text else {}


def _resolve():
    tbl = {}
    for t in api("GET", f"/api/v2/meta/bases/{BASE_ID}/tables").get("list", []):
        title = t["title"].strip().lower()
        if title in TABLES:
            tbl[title] = t["id"]
    missing = [t for t in TABLES if t not in tbl]
    if missing:
        raise RuntimeError(f"NocoDB base {BASE_ID} is missing tables: {missing}")
    lnk = {}
    for title, tid in tbl.items():
        lnk[title] = {}
        for col in api("GET", f"/api/v2/meta/tables/{tid}").get("columns", []):
            if col.get("uidt") in ("Links", "LinkToAnotherRecord"):
                lnk[title][col["title"].strip().lower()] = col["id"]
    return tbl, lnk


TBL, LNK = _resolve()


def download_attachment(att):
    url = att.get("signedUrl") or att["url"]
    if url.startswith("/"):
        url = f"{NOCODB_URL}{url}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def upload_file(filename, content):
    r = requests.post(f"{NOCODB_URL}/api/v2/storage/upload",
                      headers={"xc-token": TOKEN},
                      files={"file": (filename, content,
                             "application/vnd.openxmlformats-officedocument"
                             ".presentationml.presentation")},
                      timeout=60)
    r.raise_for_status()
    return r.json()


def active_template():
    rows = api("GET", f"/api/v2/tables/{TBL['offer_templates']}/records"
                      "?where=(active,eq,true)&sort=-Id&limit=1").get("list", [])
    if not rows:
        raise HTTPException(422, "No active template in offer_templates")
    atts = rows[0].get("file") or []
    if isinstance(atts, str):
        atts = json.loads(atts)
    if not atts:
        raise HTTPException(422, f"Template '{rows[0].get('name')}' has no file attached")
    return rows[0], download_attachment(atts[0])


# ------------------------------------------------------------- API
app = FastAPI(title="offer-service")


class GenReq(BaseModel):
    lead_id: int
    data: dict[str, Any]


@app.get("/health")
def health():
    return {"ok": True, "tables": TBL}


@app.post("/generate")
def generate(req: GenReq):
    warnings = []
    data = req.data
    lead = data.get("lead") or {}
    tpl_row, tpl_bytes = active_template()
    pptx = render_pptx(tpl_bytes, data, warnings)

    name = f"oferta_{req.lead_id}_{date.today().isoformat()}.pptx"
    attachment = upload_file(name, pptx)
    offer = api("POST", f"/api/v2/tables/{TBL['offers']}/records", json={
        "title": f"Oferta — {lead.get('contact_name', req.lead_id)}",
        "status": "draft",
        "price": lead.get("value"),
        "template_name": tpl_row.get("name"),
        "file": attachment,
        "data_json": json.dumps(data, ensure_ascii=False),
        "warnings": "\n".join(warnings) or None})
    offer_id = offer.get("Id") or offer.get("id")
    fid = LNK["offers"].get("lead")
    if fid:
        api("POST", f"/api/v2/tables/{TBL['offers']}/links/{fid}/records/{offer_id}",
            json=[{"Id": req.lead_id}])
    return {"offer_id": offer_id, "lead_id": req.lead_id,
            "template": tpl_row.get("name"), "warnings": warnings}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
