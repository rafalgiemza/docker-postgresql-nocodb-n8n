#!/usr/bin/env python3
"""offer-service: a fully generic PPTX template renderer, no NocoDB
dependency of its own — n8n (W9) supplies both the template FILE and the
DATA, this service only duplicates repeat-slides and substitutes
placeholders. n8n owns fetching the template, assembling data, uploading
the result, and creating/linking the `offers` record.

Flow (POST /render, multipart/form-data):
  - field "template": the .pptx file (from offer_templates.file)
  - field "data": JSON string, the render context (see renderer.py /
    README.md for the placeholder contract)
  -> response: the rendered .pptx as binary; warnings (if any) come back
     in the `X-Warnings` response header as a JSON array string.

Template contract (editable by non-developers in PowerPoint):
  - {{path.to.value}} anywhere, resolved by walking `data` — whatever keys
    n8n put in there (e.g. {{lead.contact_name}}, {{offer.date}}).
  - a slide with `repeat:<name>` in its SPEAKER NOTES is duplicated once
    per entry in data[<name>] (must be a list); inside it, that entry is
    exposed under the same <name>, e.g. `repeat:participant` + data with
    a "participant" list -> {{participant.full_name}} etc. <name> is
    whatever n8n calls it - nothing is hardcoded here.
  - keep each {{placeholder}} inside ONE styling run (don't bold half of
    it), otherwise the paragraph's mixed formatting collapses to the
    first run's.

Env: PORT (default 8000) — that's it, no NocoDB env vars.
"""
import json
import os

import uvicorn
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import Response

from renderer import render_pptx

app = FastAPI(title="offer-service")

PPTX_MIME = ("application/vnd.openxmlformats-officedocument"
             ".presentationml.presentation")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/render")
async def render(template: UploadFile = File(...), data: str = Form(...)):
    warnings = []
    tpl_bytes = await template.read()
    ctx = json.loads(data)
    pptx_bytes = render_pptx(tpl_bytes, ctx, warnings)
    return Response(
        content=pptx_bytes,
        media_type=PPTX_MIME,
        headers={"X-Warnings": json.dumps(warnings, ensure_ascii=True)},
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
