"""Testy czystej logiki eksportu (bez bazy)."""
import legacy_export as le

BASE = dict(
    lead_type="B2C", lead_name="Anna Anielska", p_name="Anna Anielska",
    p_email="anna@x.pl", p_phone="500000001", seller="Przemek Giemza",
    lead_source="Google", contact_channel="Mail", qualification="SQL",
    received_at="2026-10-14T14:09:00+02:00", opp_id=None, notes="")


def row(**kw):
    return le.to_row({**BASE, **kw}, 1704)


def test_header_has_32_columns_and_second_row_labels():
    assert len(le.HEADER) == 32 and len(le.HEADER2) == 32
    assert le.HEADER2[28] == "Wartość" and le.HEADER2[18] == "DEMO"


def test_dates_and_time_format():
    r = row()
    assert r[13] == "10/14/2026" and r[14] == "2:09:00 PM"
    assert r[4] == "Przemek"                       # imie z full_name


def test_midnight_time_is_empty():
    assert row(received_at="2026-10-19T00:00:00+02:00")[14] == ""


def test_notes_are_split_back_into_columns():
    notes = ("Moja notatka\nPlanowane działanie (stary CRM): zadzwonić\n"
             "Etykieta szansy (stary CRM): gorący\nSpr. ID (stary CRM): 77")
    r = row(notes=notes)
    assert r[30] == "Moja notatka"
    assert (r[27], r[29], r[31]) == ("zadzwonić", "gorący", "77")


def test_lost_lead_without_opportunity():
    r = row(notes="Utracone w starym CRM 2026-10-20: nie chce discovery")
    assert (r[25], r[26], r[23], r[24]) == ("utracona", "Utracona", "10/20/2026",
                                           "nie chce discovery")


def test_opportunity_stage_state_and_milestones():
    r = row(opp_id=5, stage="Umowa podpisana", state="won",
            p_created="2026-10-14T10:00:00+02:00",
            opp_created="2026-10-14T12:00:00+02:00",
            hist={"Audyt": "2026-10-15T12:00:00+02:00",
                  "Umowa podpisana": "2026-10-22T12:00:00+02:00"})
    assert (r[25], r[26]) == ("umowa podpisana", "Zamknięta")
    assert (r[15], r[16], r[17], r[22]) == ("10/14/2026", "10/14/2026",
                                           "10/15/2026", "10/22/2026")


def test_b2b_uses_company_in_client_and_org():
    r = row(lead_type="B2B", c_name="Alfa Sp. z o.o.", c_industry="IT")
    assert r[1] == r[2] == "Alfa Sp. z o.o." and r[5] == "IT"
