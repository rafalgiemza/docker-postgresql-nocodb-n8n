import copy, io
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.text.font import Font

import richtext
from richtext import Span
from placeholders import PLACEHOLDER, resolve

# See richtext.py for the exact markdown syntax recognized (bold/italic/
# underline/strike/code/links - headings/lists/quotes/images degrade to
# plain text for now, Phase 2/3 in .ai/offers/plan-september.md).
CODE_FONT = "Consolas"


def _apply_style(r_el, style):
    f = Font(r_el)
    f.bold = style.bold
    f.italic = style.italic
    f.underline = style.underline
    f.strike = style.strike
    if style.code:
        f.name = CODE_FONT


def _place(el, style, run, top_anchor, already_attached):
    """Attach `el` (a <w:r>, already carrying its text+style) at the
    paragraph level, wrapping it in a <w:hyperlink> when `style.link` is
    set. Returns the new top_anchor (the element subsequent siblings are
    inserted after)."""
    if style.link:
        wrapper = OxmlElement("w:hyperlink")
        rId = run.part.relate_to(style.link, RT.HYPERLINK, is_external=True)
        wrapper.set(qn("r:id"), rId)
        if already_attached:
            el.getparent().replace(el, wrapper)
        else:
            top_anchor.addnext(wrapper)
        wrapper.append(el)
        return wrapper
    if not already_attached:
        top_anchor.addnext(el)
    return el


def _apply_rich_text(run, spans):
    """Rewrite `run` in place as a richtext-aware run sequence (`spans` from
    richtext.segments()). New runs are deep-copies of the original run's XML
    (so they inherit its font/size/color) with only the toggled properties
    changed per segment; line breaks become a `<w:br/>` inside whichever run
    is current (DOCX breaks are run content, not paragraph-level siblings
    like PPTX's `<a:br/>`) - never a new `<w:p>`, same reasoning as PPTX
    (would repeat numbering/paragraph spacing)."""
    r_el = run._r
    run.text = ""
    top_anchor = r_el
    current_run_el = r_el
    used_original = False
    for tok in spans:
        if not isinstance(tok, Span):
            current_run_el.add_br()
            continue
        if not tok.text:
            continue
        if not used_original:
            el = r_el
            already_attached = True
            used_original = True
        else:
            el = copy.deepcopy(r_el)
            already_attached = False
        el.text = tok.text
        _apply_style(el, tok.style)
        top_anchor = _place(el, tok.style, run, top_anchor, already_attached)
        current_run_el = el


def render_paragraph(para, ctx, warnings):
    """Replace placeholders in paragraph text."""
    runs = para.runs
    if not runs:
        return

    full = "".join(r.text or "" for r in runs)
    if "{{" not in full:
        return

    sub = lambda s: PLACEHOLDER.sub(lambda m: resolve(m.group(1), ctx, warnings), s)

    # Fast path: every run is self-contained (no placeholder split across runs).
    if all(("{{" in (r.text or "")) == ("}}" in (r.text or "")) for r in runs) \
            and "{{" not in PLACEHOLDER.sub("", full):
        for r in runs:
            if r.text and "{{" in r.text:
                resolved = sub(r.text)
                spans = richtext.segments(resolved)
                if richtext.is_rich(spans):
                    _apply_rich_text(r, spans)
                else:
                    r.text = resolved
        return

    # Placeholder split across runs: collapse into first run.
    if runs:
        resolved = sub(full)
        spans = richtext.segments(resolved)
        if richtext.is_rich(spans):
            _apply_rich_text(runs[0], spans)
        else:
            runs[0].text = resolved
        for r in runs[1:]:
            r.text = ""


def render_docx(template_bytes, data, warnings):
    """Render a DOCX template with placeholder substitution.

    Renders {{path.to.value}} placeholders in paragraphs, tables, headers, footers.
    """
    doc = Document(io.BytesIO(template_bytes))

    # Render main document paragraphs
    for para in doc.paragraphs:
        render_paragraph(para, data, warnings)

    # Render tables in main document
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    render_paragraph(para, data, warnings)

    # Render headers and footers
    for section in doc.sections:
        # Header
        for para in section.header.paragraphs:
            render_paragraph(para, data, warnings)
        for table in section.header.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        render_paragraph(para, data, warnings)

        # Footer
        for para in section.footer.paragraphs:
            render_paragraph(para, data, warnings)
        for table in section.footer.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        render_paragraph(para, data, warnings)

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()
