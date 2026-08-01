"""Mocked integration test for app.py's NocoDB glue (api/_resolve/
download_attachment/upload_file) + the /generate handler wired to the real
renderer. `data` now arrives pre-assembled from n8n (W9) — app.py only reads
`offer_templates` and writes `offers`, no more NocoDB fetching of
leads/participants/testimonials/companies/assessments.

Run:  pytest offer-service/test_app.py -v
"""
import io
import os
from unittest.mock import MagicMock, patch

from pptx import Presentation
from pptx.util import Inches

os.environ.setdefault("NOCODB_URL", "http://nocodb-test:8080")
os.environ.setdefault("NOCODB_TOKEN", "test-token")
os.environ.setdefault("NOCODB_BASE_ID", "base1")

_TABLES_META = {"list": [
    {"title": "offer_templates", "id": "tbl_templates"},
    {"title": "offers", "id": "tbl_offers"},
]}
_COLUMNS = {
    "tbl_templates": [],
    "tbl_offers": [{"title": "lead", "uidt": "Links", "id": "c_lead"}],
}


def _fake_resolve_request(method, url, headers=None, timeout=None, **kw):
    resp = MagicMock(ok=True, text="{}")
    if url.endswith("/api/v2/meta/bases/base1/tables"):
        resp.json.return_value = _TABLES_META
    elif "/api/v2/meta/tables/" in url:
        tid = url.rsplit("/", 1)[-1]
        resp.json.return_value = {"columns": _COLUMNS[tid]}
    else:
        raise AssertionError(f"unexpected setup call: {method} {url}")
    return resp


# _resolve() runs at import time — mock the HTTP layer just for that.
with patch("requests.request", side_effect=_fake_resolve_request):
    import app


def _template_pptx_bytes():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
    box.text_frame.paragraphs[0].add_run().text = "{{lead.contact_name}}"

    repeat = prs.slides.add_slide(prs.slide_layouts[6])
    box2 = repeat.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
    box2.text_frame.paragraphs[0].add_run().text = "{{participant.full_name}} {{participant.a.o}}"
    repeat.notes_slide.notes_text_frame.text = "repeat:participants"

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def test_generate_renders_pre_assembled_data(monkeypatch):
    calls = {}

    def fake_api(method, path, **kw):
        if method == "GET" and path.startswith(f"/api/v2/tables/{app.TBL['offer_templates']}/records"):
            return {"list": [{"Id": 5, "name": "Template A",
                              "file": [{"url": "/dl/template.pptx"}]}]}
        if method == "POST" and path == f"/api/v2/tables/{app.TBL['offers']}/records":
            calls["offer_create"] = kw["json"]
            return {"Id": 99}
        if method == "POST" and path.startswith(f"/api/v2/tables/{app.TBL['offers']}/links/"):
            calls["offer_link"] = (path, kw["json"])
            return {}
        raise AssertionError(f"unexpected api() call: {method} {path}")

    monkeypatch.setattr(app, "api", fake_api)
    monkeypatch.setattr(app, "download_attachment",
                        lambda att: (calls.setdefault("dl_att", att), _template_pptx_bytes())[1])
    monkeypatch.setattr(app, "upload_file",
                        lambda name, content: calls.setdefault("uploaded", (name, content)) or [{"url": "/dl/out.pptx"}])

    payload = {
        "lead_id": 1,
        "data": {
            "lead": {"contact_name": "Ala", "value": 5000},
            "company": {"name": "Firma X"},
            "participants": [{"full_name": "Basia", "a": {"o": "B2"}}],
            "testimonials": [],
            "offer": {"date": "27.07.2026", "price": 5000, "variant": "",
                      "participants_count": 1},
        },
    }
    result = app.generate(app.GenReq(**payload))

    assert result["offer_id"] == 99
    assert result["template"] == "Template A"
    assert result["warnings"] == []
    assert calls["dl_att"] == {"url": "/dl/template.pptx"}
    assert calls["offer_create"]["title"] == "Oferta — Ala"
    assert calls["offer_create"]["status"] == "draft"
    assert calls["offer_create"]["price"] == 5000
    assert calls["offer_create"]["data_json"]  # snapshot stored verbatim
    assert calls["offer_link"][1] == [{"Id": 1}]
    rendered = Presentation(io.BytesIO(calls["uploaded"][1]))
    slides = list(rendered.slides)
    assert slides[0].shapes[0].text_frame.text == "Ala"
    assert slides[1].shapes[0].text_frame.text == "Basia B2"


def test_generate_missing_active_template_returns_422(monkeypatch):
    def fake_api(method, path, **kw):
        if method == "GET":
            return {"list": []}
        raise AssertionError("should not reach offer creation without a template")

    monkeypatch.setattr(app, "api", fake_api)

    from fastapi import HTTPException
    import pytest
    with pytest.raises(HTTPException) as exc:
        app.generate(app.GenReq(lead_id=2, data={"lead": {"contact_name": "Zenon"}}))
    assert exc.value.status_code == 422
