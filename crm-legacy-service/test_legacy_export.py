"""Testy czystej logiki eksportu (bez bazy)."""
import json
from decimal import Decimal

import legacy_export as le
import legacy_import as li

C = le.C
BASE = dict(
    lead_type="B2C", lead_name="Anna Anielska", p_name="Anna Anielska",
    p_email="anna@x.pl", p_phone="500000001", seller_id=1,
    seller_name="Przemek Giemza", lead_source="Google", contact_channel="Mail",
    qualification="SQL", received_at="2026-10-14T14:09:00+02:00", opp_id=None,
    notes="")


def row(**kw):
    sellers = kw.pop("sellers", None)
    return le.to_row({**BASE, **kw}, 1704, sellers)


def test_default_header_is_client_layout_with_33_columns():
    h = le.DEFAULT_HEADER[0]
    assert len(h) == 33 and h[27] == "Data planowanego działania"
    assert h[18] == "Data\nDEMO" and h[29].endswith("Wartość")
    assert [le.header_key(c) for c in h].count(None) == 0


def test_dates_without_zeros_and_time_format():
    r = row(received_at="2026-09-05T14:09:00+02:00")
    assert r[C["received_d"]] == "9/5/2026" and r[C["received_t"]] == "2:09:00 PM"


def test_midnight_time_is_empty():
    assert row(received_at="2026-10-19T00:00:00+02:00")[C["received_t"]] == ""


def test_seller_uses_original_text_from_meta():
    assert row(sellers={"1": "Przemek"})[C["seller"]] == "Przemek"
    assert row(seller_id=9, sellers={"1": "Przemek"})[C["seller"]] == "Przemek Giemza"
    assert row(seller_id=2, seller_name="Agnieszka",
               sellers={"2": "Agnieszka Lasoń-Kurzela"})[C["seller"]] == "Agnieszka Lasoń-Kurzela"


def test_placeholder_person_is_exported_as_empty_cells():
    r = row(lead_name="Nieznany kontakt (stary CRM #1519)",
            p_name="Nieznany kontakt (stary CRM #1519)", p_email="", p_phone="")
    assert r[C["client"]] == r[C["contact"]] == r[C["email"]] == ""


def test_notes_are_split_back_into_columns():
    notes = ("Moja notatka\nData planowanego działania (stary CRM): 11/05/2026\n"
             "Planowane działanie (stary CRM): zadzwonić\n"
             "Etykieta szansy (stary CRM): gorący\nSpr. ID (stary CRM): 77")
    r = row(notes=notes)
    assert r[C["notes"]] == "Moja notatka"
    assert (r[C["planned_d"]], r[C["planned"]], r[C["label"]], r[C["check_id"]]) == (
        "11/05/2026", "zadzwonić", "gorący", "77")


def test_values_kept_by_import_in_notes_come_back_to_their_columns():
    notes = ("Źródło (stary CRM): 36\nBranża (stary CRM): Medicine, Pharma\n"
             "Data demo (stary CRM): 22.12.205\nFolder klienta (stary CRM): B2B23")
    r = row(lead_source=None, notes=notes, opp_id=5, stage="Nowa", state="open",
            opp_created="2026-10-14T12:00:00+02:00")
    assert r[C["source"]] == "36" and r[C["industry"]] == "Medicine, Pharma"
    assert r[C["demo"]] == "22.12.205" and r[C["folder"]] == "B2B23"
    assert r[C["notes"]] == ""


def test_lost_lead_without_opportunity():
    r = row(notes="Utracone w starym CRM 2026-10-20: nie chce discovery")
    assert (r[C["stage"]], r[C["state"]], r[C["lost_d"]], r[C["loss_reason"]]) == (
        "utracona", "Utracona", "10/20/2026", "nie chce discovery")


def test_opportunity_stage_state_milestones_and_money():
    r = row(opp_id=5, stage="Umowa podpisana", state="won",
            p_created="2026-10-13T10:00:00+02:00",
            opp_created="2026-10-14T12:00:00+02:00", deal_value=Decimal("3900"),
            hist={"Audyt": "2026-10-15T12:00:00+02:00",
                  "Umowa podpisana": "2026-10-22T12:00:00+02:00"})
    assert (r[C["stage"]], r[C["state"]]) == ("umowa podpisana", "Zamknięta")
    assert (r[C["client_created"]], r[C["opp_created"]], r[C["needs"]],
            r[C["contract_signed"]]) == ("10/13/2026", "10/14/2026", "10/15/2026", "10/22/2026")
    assert r[C["value"]] == "3,900.00 PLN"


def test_cells_blank_in_the_source_stay_blank_when_derived_by_import():
    # import: brak daty wplyniecia -> data szansy; brak daty klienta -> data wplyniecia
    r = row(received_at="2026-03-07T00:00:00+01:00", opp_id=5, stage="Nowa", state="open",
            opp_created="2026-03-07T12:00:00+01:00", p_created="2026-03-07T00:00:00+01:00",
            orig={"opp_created": "3/7/2026", "segment": "B2C"})
    assert r[C["received_d"]] == "" and r[C["client_created"]] == ""
    assert r[C["opp_created"]] == "3/7/2026"
    # ten sam lead, ale plik MIAL date wplyniecia i date klienta
    r = row(received_at="2026-03-07T00:00:00+01:00", opp_id=5, stage="Nowa", state="open",
            opp_created="2026-03-07T12:00:00+01:00", p_created="2026-03-07T00:00:00+01:00",
            orig={"received_d": "3/7/2026", "client_created": "3/7/2026", "opp_created": "3/7/2026"})
    assert r[C["received_d"]] == "3/7/2026" and r[C["client_created"]] == "3/7/2026"


def test_b2b_uses_company_in_client_and_org():
    r = row(lead_type="B2B", c_name="Alfa Sp. z o.o.", c_industry="IT")
    assert r[C["client"]] == r[C["org"]] == "Alfa Sp. z o.o." and r[C["industry"]] == "IT"


def test_b2b_without_company_keeps_industry_from_person():
    r = row(lead_type="B2B", c_name=None, p_industry="IT")
    assert r[C["industry"]] == "IT" and r[C["org"]] == ""


def test_layout_follows_the_header_of_the_imported_file():
    head = [["ID", "B2B / B2C", "Kolumna1", "Kolumna3", "Folder klienta", "", "Nazwa"],
            ["", "", "", "", "", "", ""]]
    assert le.layout(head) == ["id", "segment", "contact", "email", "folder", None, None]


def test_import_notes_and_export_prefixes_agree():
    """Wszystko, co import dopisuje do notatek, eksport musi rozpoznac."""
    csv_text = "\n".join([
        "ID,B2B / B2C,Źródło,Branża,Data wpłynięcia,Data szansy sprzedaży,Data archiwizacji,"
        "Folder klienta,Planowane działanie,Szansa sprzedaży . Etykieta,Spr. ID",
        "9,B2C,36,Luxury,3/7/2026,3/7/2026,01.02.2026,F1,zadzwonić,gorący,OK"])
    rows = li.read_rows(csv_text)
    sql = li.build(rows, {n: dict(kind="fk", table="t", col="c", on_owner=True)
                          for n in li.LINKS}, [], __import__("datetime").date(2026, 10, 30),
                   lambda w: None)
    lead_sql = sql.split("INSERT INTO crm.leads")[1].split("RETURNING", 1)[0]
    notes = "\n".join(__import__("re").findall(r"[^\n']*\(stary CRM\): [^\n']*", lead_sql))
    _, extra, _ = le.split_notes(notes)
    assert extra == {"source": "36", "industry": "Luxury",
                     "folder": "F1", "archived": "01.02.2026", "planned": "zadzwonić",
                     "label": "gorący", "check_id": "OK"}


def test_ts_naive_is_warsaw_wall_time_regardless_of_machine_tz(monkeypatch):
    import os, time as _t
    monkeypatch.setenv("TZ", "UTC")
    _t.tzset()
    t = le._ts("2026-10-21T14:09:00")
    assert (t.hour, t.minute) == (14, 9)
    assert le._ts("2026-10-21T12:09:00+00:00").hour == 14   # z offsetem: przeliczenie
