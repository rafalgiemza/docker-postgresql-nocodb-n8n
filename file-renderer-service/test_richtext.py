"""Offline unit tests for richtext.py — no NocoDB, no network.

Covers the markdown syntax NocoDB's rich-text Long Text fields actually
produce (see .ai/rich-text.md) and the Phase 1 scope (bold/italic/
underline/strike/code/link at run level). Headings/lists/quotes/code-blocks/
images are exercised too, but only for "degrades to plain text, doesn't
crash" - real per-type formatting is Phase 2/3 (.ai/offers/plan-september.md).

Run:  pytest file-renderer-service/test_richtext.py -v
"""
from richtext import Span, Style, BREAK, segments, is_rich

PLAIN = Style()


def test_plain_text_is_a_single_plain_span():
    assert segments("Ala") == [Span("Ala", PLAIN)]
    assert is_rich(segments("Ala")) is False


def test_empty_string_is_a_single_empty_span():
    assert segments("") == [Span("", PLAIN)]


def test_leading_and_trailing_spaces_are_preserved():
    """mistune strips block-edge whitespace internally - segments() must
    re-attach it, or an everyday value like "Ala " would silently lose its
    trailing space."""
    assert segments(" Ala") == [Span(" Ala", PLAIN)]
    assert segments("Ala ") == [Span("Ala ", PLAIN)]
    assert segments("  both  ") == [Span("  both  ", PLAIN)]
    assert segments("   ") == [Span("   ", PLAIN)]
    for t in (" Ala", "Ala ", "  both  ", "   "):
        assert is_rich(segments(t)) is False


def test_leading_tab_does_not_trigger_indented_code_block():
    """A tab (or 4+ spaces) at the start of a line is CommonMark's "indented
    code block" - must not misfire just because a template's own literal
    prose happens to start with whitespace."""
    assert segments("\tAla") == [Span("\tAla", PLAIN)]


def test_bold():
    assert segments("przed **pogrubione** po") == [
        Span("przed ", PLAIN),
        Span("pogrubione", Style(bold=True)),
        Span(" po", PLAIN),
    ]


def test_italic():
    assert segments("przed _kursywa_ po") == [
        Span("przed ", PLAIN),
        Span("kursywa", Style(italic=True)),
        Span(" po", PLAIN),
    ]


def test_underline():
    assert segments("przed <u>podkreslenie</u> po") == [
        Span("przed ", PLAIN),
        Span("podkreslenie", Style(underline=True)),
        Span(" po", PLAIN),
    ]


def test_single_word_strikethrough():
    assert segments("przed ~slowo~ po") == [
        Span("przed ", PLAIN),
        Span("slowo", Style(strike=True)),
        Span(" po", PLAIN),
    ]


def test_multi_word_strikethrough_is_not_recognized():
    """NocoDB emits ~word~ (single tilde, single word), not GFM's ~~word~~ -
    deliberately not extended to multi-word spans, since a stray "~" in
    ordinary prose (e.g. "~10 godzin") would otherwise misfire across an
    unrelated later "~"."""
    assert segments("~dwa slowa~ bez zmian") == [Span("~dwa slowa~ bez zmian", PLAIN)]


def test_two_unrelated_tildes_do_not_combine():
    text = "~10 godzin pracy, blizej ~20 godzin~ hmm"
    assert segments(text) == [Span(text, PLAIN)]


def test_inline_code():
    assert segments("wpisz `kod` tutaj") == [
        Span("wpisz ", PLAIN),
        Span("kod", Style(code=True)),
        Span(" tutaj", PLAIN),
    ]


def test_link():
    assert segments("zobacz [tutaj](https://example.com/x) teraz") == [
        Span("zobacz ", PLAIN),
        Span("tutaj", Style(link="https://example.com/x")),
        Span(" teraz", PLAIN),
    ]


def test_combined_marks_on_one_span():
    assert segments("**_<u>wszystko naraz</u>_**") == [
        Span("wszystko naraz", Style(bold=True, italic=True, underline=True)),
    ]


def test_br_and_newline_become_break_tokens():
    assert segments("Pierwszy.<br>Drugi.\nTrzeci.") == [
        Span("Pierwszy.", PLAIN), BREAK,
        Span("Drugi.", PLAIN), BREAK,
        Span("Trzeci.", PLAIN),
    ]


def test_blank_line_between_paragraphs_is_two_breaks():
    """One blank line (a visible empty line) must stay visually distinct
    from a single newline (one break) - matches the pre-mistune behaviour
    this module replaced."""
    assert segments("para jeden\n\npara dwa") == [
        Span("para jeden", PLAIN), BREAK, BREAK, Span("para dwa", PLAIN),
    ]


def test_heading_degrades_to_plain_text_for_now():
    """Real heading styling (size/weight) is Phase 2 - for now it must not
    crash and must not leak the "#" marker into the output."""
    segs = segments("# Naglowek\n\ntresc")
    assert [s.text for s in segs if isinstance(s, Span)] == ["Naglowek", "tresc"]
    assert BREAK in segs


def test_bullet_list_degrades_to_plain_lines():
    segs = segments("- jeden\n- **dwa**\n")
    texts = [s.text for s in segs if isinstance(s, Span)]
    assert texts == ["jeden", "dwa"]
    bold_flags = [s.style.bold for s in segs if isinstance(s, Span)]
    assert bold_flags == [False, True]


def test_blockquote_degrades_to_plain_text():
    segs = segments("> cytat z **pogrubieniem**")
    assert [s.text for s in segs if isinstance(s, Span)] == ["cytat z ", "pogrubieniem"]


def test_fenced_code_block_is_monospace_per_line_not_inline_parsed():
    """Code block content is literal per CommonMark - a "**" inside it must
    NOT be interpreted as bold."""
    segs = segments("```\n**not bold**\nline2\n```")
    spans = [s for s in segs if isinstance(s, Span)]
    assert [s.text for s in spans] == ["**not bold**", "line2"]
    assert all(s.style.code for s in spans)


def test_image_degrades_to_alt_text_for_now():
    """Fetching/embedding is Phase 3 - for now the alt text stands in (and
    coalesces with its plain-text neighbours, since it carries no style of
    its own)."""
    segs = segments("obrazek: ![opis](https://example.com/a.png) koniec")
    assert segs == [Span("obrazek: opis koniec", PLAIN)]
