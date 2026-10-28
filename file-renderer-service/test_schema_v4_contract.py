"""Kontrakt danych oferty po migracji do schematu v4
(docs/archive/fable/nocodb_crm_schema_v4.md, plan: docs/archive/fable/nocodb_crm_offers_v4.md).

Następca `test_schema_v3_contract.py`. Rendererowi NIE trzeba zmieniać ani linii
kodu; ten plik przypina kształt `data`, który musi wysyłać W1 po zmianie schematu
(lead -> szansa sprzedaży, participants -> persons), oraz to, co dziś W1 pomija.
Testy z prawdziwym szablonem (`init-data/source/ofer-template-1.0.pptx`, 32 MB,
poza gitem) są pomijane, gdy pliku nie ma.

Run:  pytest file-renderer-service/test_schema_v4_contract.py -v
"""
import io
import re
from pathlib import Path

import pytest
from pptx import Presentation
from pptx.util import Inches

from renderer import render_pptx

REAL_TEMPLATE = Path(__file__).resolve().parent.parent / "init-data" / "source" / "ofer-template-1.0.pptx"
needs_real_template = pytest.mark.skipif(
    not REAL_TEMPLATE.exists(), reason="prawdziwy szablon oferty nie jest w repo (init-data/source/ jest w .gitignore)")


def _add_slide(prs, text, notes=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(2))
    box.text_frame.paragraphs[0].add_run().text = text
    if notes is not None:
        slide.notes_slide.notes_text_frame.text = notes
    return slide


def _render_synthetic(prs, data, warnings):
    buf = io.BytesIO()
    prs.save(buf)
    return Presentation(io.BytesIO(render_pptx(buf.getvalue(), data, warnings)))


def _text(slide):
    return slide.shapes[0].text_frame.text


# --------------------------------------------------------------------------
# Kształt, który W1 v4 składa z danych v4:
#   lead.contact_name   <- sale_opportunities.person (kupujący) .full_name
#   assessment.*, a.*   <- najnowsza ocena pierwszej osoby oferty (persons.assessments)
#   offer.*             <- wiersz oferty (hours, total_price) + dzisiejsza data
#   package.hours       <- pierwszy wybrany pakiet (selected_package_variants_cores)
#   <Wariant>.price     <- wiersze cennika (offers.pricing)
#   testimonial(s)      <- offers.selected_testimonials
# --------------------------------------------------------------------------
TESTIMONIALS = [
    {"content": "Bardzo konkretne zajęcia", "name": "Jan K.", "position": "CTO"},
    {"content": "Poprawiliśmy negocjacje", "name": "Anna N.", "position": "CEO"},
]
DATA_V4 = {
    "lead": {"contact_name": "Piotr Zieliński"},
    "company": {"name": "ACME", "communication_processes": "demo dla klientów US"},
    "assessment": {"needs_summary": "Potrzebuje swobody w demo.", "position": "Developer"},
    "a": {"o": "B2.4", "r": "B2", "a": "B2", "f": "B1", "c": "B2"},
    "offer": {"date": "01.08.2026", "hours": 60, "price": 20400},
    "package": {"hours": 40},
    "BusinessEnglish15h": {"price": 3000},
    "BusinessEnglish15hinpair": {"price": 2000},
    "skills1on1": {"price": 1500},
    "skillsgroup": {"price": 900},
    # dwa klucze naraz: slajdy 16 i 24 szablonu używają `testimonial` (jeden),
    # slajd 25 jest `repeat:testimonials` (lista)
    "testimonial": TESTIMONIALS[0],
    "testimonials": TESTIMONIALS,
    # nazwa listy = prefiks w szablonie ({{participant.x}}), tak jak w kontrakcie v3
    "participant": [
        {"full_name": "Piotr", "position": "Dev", "a": {"o": "B2.4"},
         "assessment": {"needs_summary": "demo", "strengths": "słownictwo", "gaps": "articles"},
         "recommendation": {"type": "business_english", "headline": "BE + Skills",
                            "rationale": "bo demo", "priority": "wysoki"}},
        {"full_name": "Anna", "position": "PO", "a": {"o": "C1.0"},
         "assessment": {"needs_summary": "negocjacje", "strengths": "płynność", "gaps": "rejestr"},
         "recommendation": {"type": "skills_only", "headline": "Negocjacje",
                            "rationale": "bo kontrakty", "priority": "średni"}},
    ],
}


def test_participants_from_persons_resolve_prefixed_and_lifted():
    """v4: uczestnicy oferty to `persons` z rekomendacji; dane zagnieżdżone pod
    osobą, tak jak w v3 (prefiks `participant.` oraz klucze podniesione)."""
    prs = Presentation()
    _add_slide(prs, "{{participant.full_name}}: {{participant.recommendation.headline}} / "
                    "{{recommendation.type}} / {{assessment.gaps}} / {{a.o}}",
               notes="repeat:participant")
    warnings = []
    out = _render_synthetic(prs, {"participant": DATA_V4["participant"]}, warnings)
    assert [_text(s) for s in out.slides] == [
        "Piotr: BE + Skills / business_english / articles / B2.4",
        "Anna: Negocjacje / skills_only / rejestr / C1.0",
    ]
    assert warnings == []


def test_testimonials_list_and_single_object_serve_different_slides():
    """Stały slajd czyta `testimonial.*` z POJEDYNCZEGO obiektu; slajd z
    `repeat:testimonials` w każdej kopii czyta element listy pod prefiksem
    `testimonials.*` (nazwa znacznika) albo z kluczy podniesionych (`name`)."""
    prs = Presentation()
    _add_slide(prs, "{{testimonial.name}}")                                       # stały
    _add_slide(prs, "{{testimonials.name}} / {{testimonials.content}}", notes="repeat:testimonials")
    warnings = []
    out = _render_synthetic(prs, {"testimonial": TESTIMONIALS[0], "testimonials": TESTIMONIALS},
                            warnings)
    assert [_text(s) for s in out.slides] == [
        "Jan K.", "Jan K. / Bardzo konkretne zajęcia", "Anna N. / Poprawiliśmy negocjacje"]
    assert warnings == []


def test_singular_prefix_inside_plural_repeat_repeats_one_testimonial():
    """PUŁAPKA szablonu v1.0 (slajd 25): `repeat:testimonials` + `{{testimonial.x}}`.
    Prefiks liczby pojedynczej to osobny, GLOBALNY obiekt, więc każda kopia slajdu
    pokazuje tę samą referencję. Poprawka w szablonie: `{{testimonials.x}}`."""
    prs = Presentation()
    _add_slide(prs, "{{testimonial.name}}", notes="repeat:testimonials")
    warnings = []
    out = _render_synthetic(prs, {"testimonial": TESTIMONIALS[0], "testimonials": TESTIMONIALS},
                            warnings)
    assert [_text(s) for s in out.slides] == ["Jan K.", "Jan K."]


def test_price_keys_are_top_level_objects():
    """Ceny wariantów to obiekty na wierzchu `data` (`{{skills1on1.price}}`), nie
    lista: n8n musi zbudować je z wierszy `pricing` (offers.pricing)."""
    prs = Presentation()
    _add_slide(prs, "{{BusinessEnglish15h.price}} / {{skills1on1.price}}")
    warnings = []
    out = _render_synthetic(prs, DATA_V4, warnings)
    assert _text(list(out.slides)[0]) == "3000 / 1500"
    assert warnings == []


def test_single_package_object_not_list():
    """`{{package.hours}}` poza `repeat:` czyta OBIEKT `package`. Lista `packages`
    (tak dziś wysyła W1) go nie zasili."""
    prs = Presentation()
    _add_slide(prs, "ETAP 1: {{package.hours}}h")
    warnings = []
    out = _render_synthetic(prs, {"packages": [{"hours": 40}]}, warnings)
    assert any("package.hours" in w for w in warnings)
    warnings = []
    out = _render_synthetic(prs, {"package": {"hours": 40}}, warnings)
    assert _text(list(out.slides)[0]) == "ETAP 1: 40h" and warnings == []


# -------------------------------------------------------------- prawdziwy szablon
EXPECTED_PLACEHOLDERS = {
    "lead.contact_name", "assessment.position", "assessment.needs_summary",
    "a.o", "a.r", "a.a", "a.f", "a.c",
    "offer.date", "offer.hours", "offer.price", "package.hours",
    "BusinessEnglish15h.price", "BusinessEnglish15hinpair.price",
    "skills1on1.price", "skillsgroup.price",
    "testimonial.content", "testimonial.name", "testimonial.position",
}


@needs_real_template
def test_real_template_demands_exactly_these_placeholders():
    """Zmiana szablonu (nowy placeholder) ma wywalić ten test i wymusić decyzję,
    skąd W1 weźmie dane."""
    warnings = []
    render_pptx(REAL_TEMPLATE.read_bytes(), {}, warnings)
    missing = {re.sub(r"^.*value: ", "", w) for w in warnings if "missing placeholder value" in w}
    assert missing == EXPECTED_PLACEHOLDERS


@needs_real_template
def test_real_template_renders_clean_with_v4_data():
    warnings = []
    out = Presentation(io.BytesIO(render_pptx(REAL_TEMPLATE.read_bytes(), DATA_V4, warnings)))
    assert warnings == []
    assert len(out.slides) == 29    # 28 w szablonie + 1 za drugi testimonial


def _all_text(shapes):
    for sh in shapes:
        if sh.shape_type == 6:                       # grupa
            yield from _all_text(sh.shapes)
        elif sh.has_text_frame:
            yield sh.text_frame.text


@needs_real_template
@pytest.mark.xfail(strict=True, reason="szablon v1.0: slajd 25 (repeat:testimonials) używa "
                   "{{testimonial.*}} zamiast {{testimonials.*}}, więc obie kopie pokazują "
                   "tę samą referencję; slajd 24 ma też literówkę {{testimonial.name} "
                   "(brakuje nawiasu). Test przejdzie po poprawce szablonu.")
def test_real_template_repeat_slides_show_distinct_testimonials():
    out = Presentation(io.BytesIO(render_pptx(REAL_TEMPLATE.read_bytes(), DATA_V4, [])))
    slides = list(out.slides)
    first, second = ("".join(_all_text(slides[i].shapes)) for i in (24, 25))
    assert "Jan K." in first and "Anna N." in second
    assert not any("{{" in t for sl in slides for t in _all_text(sl.shapes))


# Kształt, który W1 wysyła DZIŚ (docs/archive/fable/W1_generate_offer.json,
# węzeł "Assemble offer data"). Charakterystyka luk, usuń po przepisaniu W1.
CURRENT_W1_DATA = {
    "key": "boy",
    "lead": {"contact_name": "Piotr Zieliński"},
    "offer": {"date": "01.08.2026", "hours": 60, "price": 20400},
    "assessment": {"needs_summary": "demo", "position": "Dev"},
    "a": {"o": "B2.4", "r": "B2", "a": "B2", "f": "B1", "c": "B2"},
    "recomendation": {"headline": "BE", "rationale": "bo"},
    "participants": [{"full_name": "Piotr", "position": "Dev"}],
    "packages": [{"title": "Core", "description": "opis", "hours": 40}],
    "adons": [{"key": "facilitating", "name": "Facilitating", "description": "x", "hours": 20}],
    "logo_wall": [{"key": "style1"}],
}


@needs_real_template
def test_current_w1_shape_leaves_known_gaps():
    warnings = []
    out = Presentation(io.BytesIO(render_pptx(REAL_TEMPLATE.read_bytes(), CURRENT_W1_DATA, warnings)))
    joined = " | ".join(warnings)
    assert "repeat:testimonials slide dropped" in joined      # W1 nie wysyła referencji
    assert "package.hours" in joined                          # lista `packages`, szablon chce `package`
    for key in ("BusinessEnglish15h.price", "skills1on1.price"):
        assert key in joined                                  # W1 nie czyta cennika
    assert len(out.slides) == 27                              # slajd z referencjami wypadł
