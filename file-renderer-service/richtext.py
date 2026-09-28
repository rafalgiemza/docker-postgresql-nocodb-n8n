import re
from dataclasses import dataclass, replace

import mistune

# LongText (rich text/markdown) fields from NocoDB come back with this exact
# syntax (verified empirically, see .ai/rich-text.md) - two of the four inline
# marks are NON-standard, no markdown parser recognizes them out of the box:
#   bold          **text**
#   italic        _text_
#   underline     <u>text</u>   (raw HTML passthrough - markdown has no mark)
#   strikethrough ~word~        (single tilde, single word - NOT GFM's ~~text~~)
# <br> is normalized to "\n" before parsing; both become a BREAK token (same
# paragraph, soft line break) - never a new paragraph, to match how mistune
# treats a single blank line as "next block", not "N literal newlines".
BR_RE = re.compile(r"<br\s*/?>", re.I)
OPEN_U_RE = re.compile(r"^<u(\s[^>]*)?>$", re.I)
CLOSE_U_RE = re.compile(r"^</u\s*>$", re.I)
# Single word only (deliberate, per NocoDB's ~word~ vs GFM's ~~word~~): no
# whitespace allowed inside, so "~10 godzin" (a plausible approximation in
# offer prose) can't accidentally span two unrelated tildes.
STRIKE_PATTERN = r"~(?!\s)[^\s~]+~"


def _parse_strike(inline, m, state):
    # m.group(1) would be a numbered group in mistune's COMBINED scanner
    # regex (all registered rules alternated together), not "our" group -
    # must slice the full match instead, same convention as the built-in
    # superscript/subscript plugins.
    state.append_token({"type": "strike", "raw": m.group(0)[1:-1]})
    return m.end()


def _strike_plugin(md):
    md.inline.register("strike", STRIKE_PATTERN, _parse_strike, before="linebreak")


_markdown = mistune.create_markdown(renderer=None, plugins=[_strike_plugin])


@dataclass(frozen=True)
class Style:
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    code: bool = False
    link: str = None


@dataclass(frozen=True)
class Span:
    text: str
    style: Style


BREAK = ("break",)
_PLAIN = Style()


def is_rich(spans):
    """True if `spans` (from segments()) is anything other than the trivial
    single-plain-span case - lets callers keep the no-op fast path for
    ordinary values instead of gratuitously splitting runs."""
    return not (len(spans) == 1 and isinstance(spans[0], Span) and spans[0].style == _PLAIN)


_LEADING_WS = re.compile(r"^[ \t]+")
_TRAILING_WS = re.compile(r"[ \t]+$")


def segments(text):
    """Parse `text` into a flat list of Span/BREAK tokens, one Span per run
    of uniform styling. `text` is the ALREADY-RESOLVED placeholder text
    (literal surrounding template text + substituted value) - markdown in
    the template's own prose is parsed too, same as bold was before this
    module existed (documented tradeoff, not new).

    Leading/trailing spaces/tabs are stripped before handing text to mistune
    and re-attached as plain text afterwards: mistune strips block edges
    itself (would silently eat a meaningful trailing space in e.g. "Ala "),
    and 4+ leading spaces or a tab would otherwise be parsed as an indented
    code block - neither is something a resolved placeholder value should
    trigger by accident.
    """
    text = BR_RE.sub("\n", text)
    lead_m = _LEADING_WS.match(text)
    lead_ws = lead_m.group(0) if lead_m else ""
    rest = text[len(lead_ws):]
    trail_m = _TRAILING_WS.search(rest)
    trail_ws = trail_m.group(0) if trail_m else ""
    core = rest[:len(rest) - len(trail_ws)] if trail_ws else rest

    tokens = _flatten_blocks(_markdown(core)) if core else []
    if lead_ws:
        tokens = [Span(lead_ws, _PLAIN)] + tokens
    if trail_ws:
        tokens = tokens + [Span(trail_ws, _PLAIN)]
    tokens = _coalesce(tokens)
    return tokens if tokens else [Span("", _PLAIN)]


def _coalesce(tokens):
    """Merge adjacent same-style Spans into one (e.g. a plain value with a
    trailing space would otherwise come out as two Spans purely because the
    whitespace-preservation above re-attaches it separately) - keeps
    is_rich() from treating ordinary values as needing a run split."""
    out = []
    for tok in tokens:
        if out and isinstance(out[-1], Span) and isinstance(tok, Span) and out[-1].style == tok.style:
            out[-1] = Span(out[-1].text + tok.text, tok.style)
        else:
            out.append(tok)
    return out


def _flatten_blocks(blocks):
    tokens = []
    first = True
    for block in blocks:
        if block["type"] == "blank_line":
            continue
        if not first:
            # Matches the pre-mistune behaviour: one blank line between two
            # paragraphs produced TWO consecutive breaks (a visible empty
            # line), not one - see test_br_and_newline_... for the single-
            # newline (one break) case this must not regress.
            tokens.append(BREAK)
            tokens.append(BREAK)
        first = False
        tokens.extend(_flatten_block(block))
    return tokens


def _flatten_block(block):
    t = block["type"]
    if t in ("paragraph", "heading"):
        return _flatten_inlines(block["children"], _PLAIN)
    if t == "block_quote":
        return _flatten_blocks(block["children"])
    if t == "list":
        out = []
        for i, item in enumerate(block["children"]):
            if i:
                out.append(BREAK)
            out.extend(_flatten_list_item(item["children"]))
        return out
    if t == "block_code":
        # Not inline-parsed (code content is literal, per CommonMark) - only
        # the code font is applied, no nested marks.
        lines = block["raw"].rstrip("\n").split("\n")
        out = []
        for i, line in enumerate(lines):
            if i:
                out.append(BREAK)
            if line:
                out.append(Span(line, replace(_PLAIN, code=True)))
        return out
    if t == "thematic_break":
        return []
    return []


def _flatten_list_item(children):
    out = []
    for i, child in enumerate(children):
        if i:
            out.append(BREAK)
        if child["type"] == "block_text":
            out.extend(_flatten_inlines(child["children"], _PLAIN))
        else:
            out.extend(_flatten_block(child))
    return out


def _flatten_inlines(children, style):
    out = []
    cur = style
    for node in children:
        t = node["type"]
        if t == "text":
            if node["raw"]:
                out.append(Span(node["raw"], cur))
        elif t == "strong":
            out.extend(_flatten_inlines(node["children"], replace(cur, bold=True)))
        elif t == "emphasis":
            out.extend(_flatten_inlines(node["children"], replace(cur, italic=True)))
        elif t == "strike":
            if node["raw"]:
                out.append(Span(node["raw"], replace(cur, strike=True)))
        elif t == "codespan":
            if node["raw"]:
                out.append(Span(node["raw"], replace(cur, code=True)))
        elif t in ("linebreak", "softbreak"):
            out.append(BREAK)
        elif t == "inline_html":
            raw = node.get("raw", "")
            if OPEN_U_RE.match(raw):
                cur = replace(cur, underline=True)
            elif CLOSE_U_RE.match(raw):
                cur = replace(cur, underline=False)
            # Any other raw inline HTML: no-op (dropped), same "unsupported
            # stays inert, doesn't crash" convention as everything else here.
        elif t == "link":
            url = node.get("attrs", {}).get("url")
            out.extend(_flatten_inlines(node["children"], replace(cur, link=url)))
        elif t == "image":
            # Fetching/embedding is Phase 3 - degrade to the alt text for now.
            out.extend(_flatten_inlines(node.get("children", []), cur))
        elif "children" in node:
            out.extend(_flatten_inlines(node["children"], cur))
        elif node.get("raw"):
            out.append(Span(node["raw"], cur))
    return out
