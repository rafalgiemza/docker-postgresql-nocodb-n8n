"""Offline unit tests for docx_renderer.py — no NocoDB, no network.

Run:  pytest file-renderer-service/test_docx_renderer.py -v
"""
import io

from docx import Document
from docx.shared import Inches

from docx_renderer import render_docx


def _new_doc():
    return Document()


def _add_paragraph(doc, text):
    """Add a paragraph with a single run."""
    p = doc.add_paragraph(text)
    return p


def _add_table_with_text(doc, rows, cols, texts):
    """Add a table with text in cells. texts is a flat list."""
    table = doc.add_table(rows=rows, cols=cols)
    i = 0
    for row in table.rows:
        for cell in row.cells:
            if i < len(texts):
                cell.paragraphs[0].text = texts[i]
                i += 1
    return table


def _render(doc, data, warnings):
    """Render doc and return Document object."""
    buf = io.BytesIO()
    doc.save(buf)
    rendered_bytes = render_docx(buf.getvalue(), data, warnings)
    return Document(io.BytesIO(rendered_bytes))


def test_simple_placeholder_in_paragraph():
    doc = _new_doc()
    _add_paragraph(doc, "Hello {{lead.name}}")
    warnings = []
    out = _render(doc, {"lead": {"name": "Alice"}}, warnings)
    assert out.paragraphs[0].text == "Hello Alice"
    assert warnings == []


def test_missing_placeholder_becomes_empty_and_warns():
    doc = _new_doc()
    _add_paragraph(doc, "Hello {{lead.name}}")
    warnings = []
    out = _render(doc, {"lead": {}}, warnings)
    assert out.paragraphs[0].text == "Hello "
    assert any("lead.name" in w for w in warnings)


def test_nested_placeholder():
    doc = _new_doc()
    _add_paragraph(doc, "Contact: {{lead.person.email}}")
    warnings = []
    out = _render(doc, {"lead": {"person": {"email": "alice@example.com"}}}, warnings)
    assert out.paragraphs[0].text == "Contact: alice@example.com"
    assert warnings == []


def test_placeholder_in_table_cell():
    doc = _new_doc()
    _add_table_with_text(doc, 2, 2, ["Name", "{{person.name}}", "Email", "{{person.email}}"])
    warnings = []
    out = _render(doc, {"person": {"name": "Bob", "email": "bob@ex.com"}}, warnings)

    table = out.tables[0]
    cells = [cell.text for row in table.rows for cell in row.cells]
    assert cells == ["Name", "Bob", "Email", "bob@ex.com"]
    assert warnings == []


def test_multiple_placeholders_in_one_paragraph():
    doc = _new_doc()
    _add_paragraph(doc, "{{title}}: {{value}} ({{unit}})")
    warnings = []
    out = _render(doc, {"title": "Price", "value": "100", "unit": "PLN"}, warnings)
    assert out.paragraphs[0].text == "Price: 100 (PLN)"
    assert warnings == []


def test_no_placeholder_leaves_text_unchanged():
    doc = _new_doc()
    _add_paragraph(doc, "This is plain text")
    warnings = []
    out = _render(doc, {}, warnings)
    assert out.paragraphs[0].text == "This is plain text"
    assert warnings == []


def test_float_converted_to_int_if_whole():
    doc = _new_doc()
    _add_paragraph(doc, "Value: {{amount}}")
    warnings = []
    out = _render(doc, {"amount": 42.0}, warnings)
    assert out.paragraphs[0].text == "Value: 42"
    assert warnings == []


def test_float_with_decimal_stays_float():
    doc = _new_doc()
    _add_paragraph(doc, "Value: {{amount}}")
    warnings = []
    out = _render(doc, {"amount": 42.5}, warnings)
    assert out.paragraphs[0].text == "Value: 42.5"
    assert warnings == []
