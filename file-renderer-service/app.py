#!/usr/bin/env python3
"""file-renderer-service: generic template renderers for PPTX and DOCX, no NocoDB
dependency of its own — n8n supplies both the template FILE and the DATA,
this service only substitutes placeholders (and duplicates repeat-slides for PPTX).
n8n owns fetching the template, assembling data, uploading the result.

Flow:
  POST /render (PPTX):
    - field "template": the .pptx file
    - field "data": JSON string, the render context
    -> rendered .pptx as binary; warnings in X-Warnings header

  POST /render-docx (DOCX):
    - field "template": the .docx file
    - field "data": JSON string, the render context
    -> rendered .docx as binary; warnings in X-Warnings header

Template contract (editable by non-developers):
  - {{path.to.value}} anywhere, resolved by walking `data`
  - PPTX only: slide with `repeat:<name>` in SPEAKER NOTES duplicates for each
    item in data[<name>] (must be a list)
  - keep {{placeholder}} inside ONE styling run (don't bold half of it)

Env: PORT (default 8000)
"""
import json
import os

import uvicorn
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import Response

from renderer import render_pptx
from docx_renderer import render_docx

app = FastAPI(title="file-renderer-service")

PPTX_MIME = ("application/vnd.openxmlformats-officedocument"
             ".presentationml.presentation")
DOCX_MIME = ("application/vnd.openxmlformats-officedocument"
             ".wordprocessingml.document")


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


@app.post("/render-docx")
async def render_document(template: UploadFile = File(...), data: str = Form(...)):
    warnings = []
    tpl_bytes = await template.read()
    ctx = json.loads(data)
    docx_bytes = render_docx(tpl_bytes, ctx, warnings)
    return Response(
        content=docx_bytes,
        media_type=DOCX_MIME,
        headers={"X-Warnings": json.dumps(warnings, ensure_ascii=True)},
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
