"""Mocked integration test for app.py's NocoDB glue (api/_resolve/get_record/
get_linked/download_attachment/upload_file) + the /generate handler wired
to the real renderer. No network, no live NocoDB — fills the gap left by
app.py originally referencing these helpers without defining them.

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
    {"title": "leads", "id": "tbl_leads"},
    {"title": "participants", "id": "tbl_participants"},
    {"title": "testimonials", "id": "tbl_testimonials"},
    {"title": "companies", "id": "tbl_companies"},
    {"title": "offer_templates", "id": "tbl_templates"},
    {"title": "offers", "id": "tbl_offers"},
]}
_COLUMNS = {
    "tbl_leads": [{"title": "participants", "uidt": "Links", "id": "c_part"},
                  {"title": "selected_testimonials", "uidt": "Links", "id": "c_test"},
                  {"title": "company", "uidt": "Links", "id": "c_comp"}],
    "tbl_offers": [{"title": "lead", "uidt": "Links", "id": "c_lead"}],
    "tbl_participants": [], "tbl_testimonials": [], "tbl_companies": [],
    "tbl_templates": [],
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
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def test_generate_end_to_end_with_mocked_nocodb(monkeypatch):
    calls = {}

    def fake_get_record(table, rid):
        assert (table, rid) == ("leads", 1)
        return {"Id": 1, "contact_name": "Ala", "value": 5000}

    def fake_get_linked(table, field, rid):
        assert table == "leads" and rid == 1
        if field == "participants":
            return [{"Id": 10, "full_name": "Basia"}]
        return []

    def fake_api(method, path, **kw):
        if method == "GET" and path.startswith(f"/api/v2/tables/{app.TBL['offer_templates']}/records"):
            return {"list": [{"Id": 5, "name": "Template A",
                              "file": [{"url": "/dl/template.pptx"}]}]}
        if method == "POST" and path == f"/api/v2/tables/{app.TBL['offers']}/records":
            calls["offer_create"] = kw["json"]
            return {"Id": 99}
        if method == "POST" and path.startswith(
                f"/api/v2/tables/{app.TBL['offers']}/links/"):
            calls["offer_link"] = (path, kw["json"])
            return {}
        raise AssertionError(f"unexpected api() call: {method} {path}")

    def fake_download_attachment(att):
        assert att == {"url": "/dl/template.pptx"}
        return _template_pptx_bytes()

    def fake_upload_file(filename, content):
        calls["uploaded"] = (filename, content)
        return [{"url": "/dl/out.pptx", "title": filename}]

    monkeypatch.setattr(app, "get_record", fake_get_record)
    monkeypatch.setattr(app, "get_linked", fake_get_linked)
    monkeypatch.setattr(app, "api", fake_api)
    monkeypatch.setattr(app, "download_attachment", fake_download_attachment)
    monkeypatch.setattr(app, "upload_file", fake_upload_file)

    result = app.generate(app.GenReq(lead_id=1))

    assert result["offer_id"] == 99
    assert result["template"] == "Template A"
    assert result["warnings"] == []
    assert calls["offer_create"]["title"] == "Oferta — Ala"
    assert calls["offer_create"]["status"] == "draft"
    assert calls["offer_create"]["price"] == 5000
    assert calls["offer_link"][1] == [{"Id": 1}]
    # renderer actually ran against the mocked template bytes:
    rendered = Presentation(io.BytesIO(calls["uploaded"][1]))
    assert rendered.slides[0].shapes[0].text_frame.text == "Ala"


def test_generate_warns_when_lead_has_no_participants(monkeypatch):
    monkeypatch.setattr(app, "get_record", lambda t, r: {"Id": 2, "contact_name": "Zenon"})
    monkeypatch.setattr(app, "get_linked", lambda t, f, r: [])

    def fake_api(method, path, **kw):
        if method == "GET":
            return {"list": [{"Id": 5, "name": "Template A", "file": [{"url": "/x"}]}]}
        if "records" in path and "links" not in path:
            return {"Id": 100}
        return {}

    monkeypatch.setattr(app, "api", fake_api)
    monkeypatch.setattr(app, "download_attachment", lambda att: _template_pptx_bytes())
    monkeypatch.setattr(app, "upload_file", lambda name, content: [{"url": "/x"}])

    result = app.generate(app.GenReq(lead_id=2))
    assert "lead has no participants linked" in result["warnings"]
