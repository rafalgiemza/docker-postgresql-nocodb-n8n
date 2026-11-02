"""Testy czystej logiki importu (bez bazy): daty, mapowanie, generowany SQL."""
import json
from datetime import date
from pathlib import Path

import pytest

import legacy_import as li

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "docs" / "crm" / "crm-utf-8.csv"
EXPORT = date(2026, 10, 30)


def parse(s):
    w = []
    return li.parse_date(s, EXPORT, w.append, "t"), w


def test_mdy_is_default():
    assert parse("10/21/2026")[0] == date(2026, 10, 21)


def test_future_mdy_falls_back_to_dmy_with_warning():
    d, w = parse("12/10/2026")
    assert d == date(2026, 10, 12) and len(w) == 1


def test_garbage_date_is_skipped():
    d, w = parse("wczoraj")
    assert d is None and w


def test_decode_cp1252_fallback():
    assert li.decode("zażółć".encode("cp1252", errors="ignore")) is not None
    assert li.decode("Śląsk".encode("utf-8")) == "Śląsk"


def test_loss_and_disqualify_reasons():
    assert li.loss_reason("Price too high") == "cena"
    assert li.disq_reason("na razie nie ma odpowiedzi") == "brak_kontaktu"
    assert li.disq_reason("") is None


def test_money():
    assert li.money("1 234,50 zł") == "1234.50"
    assert li.money("3,900.00 PLN") == "3900.00"
    assert li.money("10,500.00 PLN") == "10500.00"
    assert li.money("0.00 PLN") == "0.00"
    assert li.money("4800") == "4800.00"
    assert li.money("1.234.567,89") == "1234567.89"
    assert li.money("") is None


def fake_links():
    sm = json.loads((ROOT / "docs/archive/fable/schema_map.json").read_text())
    links = {}
    for name, (t, f) in li.LINKS.items():
        m = sm[t]["fields"][f]
        links[name] = dict(kind="junction", table=m["junction_table_name"],
                           owner=f"{t}_id", other=f"{m['related_table']}_id",
                           single=m["relation_type"] == "mo")
    return links


@pytest.mark.skipif(not SAMPLE.exists(), reason="brak pliku probki")
def test_sample_builds_expected_sql():
    rows = li.read_rows(li.decode(SAMPLE.read_bytes()))
    warns = []
    sql = li.build(rows, fake_links(), [(1, "Przemek Giemza")], EXPORT, warns.append)
    assert len(rows) == 10
    assert sql.count("INSERT INTO crm.leads") == 10
    assert sql.count("INSERT INTO crm.sale_opportunities") == 5  # tylko z "Data szansy"
    assert "'2026-10-12T" in sql                                # 1704: 10/12/2026
    assert "'Umowa podpisana'" in sql and "'Utracona'" in sql
    assert warns == []                                           # czysty plik MM/DD


def _client_csv(extra_cols=0, with_planned_d=True):
    """Plik w ukladzie klienta: jednowierszowy naglowek z nowymi liniami,
    33 kolumny, ewentualnie puste kolumny na koncu (Excel)."""
    import csv, io
    head = ["ID", "Nazwa klienta", "Organizacja", "B2B / B2C", "Handlowiec",
            "Branża", "Źródło", "Forma\nkontaktu", "Kwalifikacja lead'a",
            "Powód braku kwalifikacji lead'a", "Osoba kontaktowa", "Nr telefonu",
            "E.mail", "Data\nwpłynięcia", "Godzina\nwpłynięcia",
            "Data utworzenia klienta", "Data szansy sprzedaży",
            "Data badania potrzeb", "Data\nDEMO", "Data wysłania oferty",
            "Data omówienia oferty", "Data wysłania umowy",
            "Data podpisania umowy", "Data\nutracenia", "Powód utraty szansy",
            "Etap", "Stan", "Data planowanego działania", "Planowane działanie",
            "Szansa sprzedaży \nWartość", "Szansa sprzedaży . Etykieta", "Notatki",
            "Spr. ID"]
    row = [""] * 33
    row[0], row[1], row[3], row[10] = "1801", "Jan Test", "B2C", "Jan Test"
    row[12], row[13], row[27] = "jan@example.com", "10/21/2026", "11/05/2026"
    row[28] = "zadzwonić"
    if not with_planned_d:
        head.pop(27); row.pop(27)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(head + [""] * extra_cols)
    w.writerow(row + [""] * extra_cols)
    return buf.getvalue()


def test_client_layout_33_columns_with_trailing_empty_columns():
    rows = li.read_rows(_client_csv(extra_cols=4))
    assert len(rows) == 1 and len(rows[0]) == li.N_ROW
    assert rows[0][li.C["planned_d"]] == "11/05/2026"
    assert rows[0][li.C["planned"]] == "zadzwonić"


def test_old_32_column_layout_still_accepted():
    rows = li.read_rows(_client_csv(with_planned_d=False))
    assert rows[0][li.C["planned_d"]] == "" and rows[0][li.C["planned"]] == "zadzwonić"


def test_missing_required_header_lists_what_was_found():
    import csv, io
    buf = io.StringIO(); csv.writer(buf).writerow(["ID", "A", "B"])
    with pytest.raises(li.LegacyError, match="brak wymaganych.*'b2b / b2c'.*'a'"):
        li.read_rows(buf.getvalue())


def _big_header():
    return ["ID", "Nazwa klienta", "Organizacja", "Folder klienta", "B2B / B2C",
            "Handlowiec ", "Branża", "Źródło", "Forma kontaktu",
            "Kwalifikacja lead'a", "Powód braku kwalifikacji lead'a", "Kolumna1",
            "Kolumna2", "Kolumna3", "Data wpłynięcia", "Godzina wpłynięcia",
            "Data utworzenia klienta", "Data szansy sprzedaży", "Data archiwizacji",
            "Data badania potrzeb", "Data DEMO", "Data wysłania oferty",
            "Data omówienia oferty", "Data wysłania umowy", "Data podpisania umowy",
            "Data utracenia", "Powód utraty szansy", "Etap", "Stan",
            "Data planowanego działania", "Planowane działanie",
            "Szansa sprzedaży Wartość", "Szansa sprzedaży . Etykieta", "Notatki",
            "Spr. ID", "", "", "", ""]


def _big_csv(**cells):
    import csv, io
    head = _big_header()
    row = [""] * len(head)
    for k, v in {"ID": "1519", "B2B / B2C": "B2C", "Handlowiec ": "Natalia",
                 "Data szansy sprzedaży": "3/7/2024", "Stan": "Otwarta",
                 "Szansa sprzedaży Wartość": "3,900.00 PLN", **cells}.items():
        row[head.index(k)] = v
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(head); w.writerow(row)
    w.writerow(["-1"] + [""] * 38)
    return buf.getvalue()


def test_big_file_layout_by_header_names():
    rows, notes = li.read_table(_big_csv(**{"Folder klienta": "B2"}))
    assert len(rows) == 1                      # ujemne ID pominiete
    r = rows[0]
    assert r[li.C["opp_created"]] == "3/7/2024" and r[li.C["seller"]] == "Natalia"
    assert r[li.C["value"]] == "3,900.00 PLN" and r[li.C["folder"]] == "B2"
    assert any("1 wierszy bez poprawnego" in n for n in notes)


def test_big_file_without_received_date_uses_opportunity_date():
    rows = li.read_rows(_big_csv())
    w = []
    sql = li.build(rows, fake_links(), [(1, "Natalia Test")], EXPORT, w.append)
    assert "'2024-03-07T00:00:00+01:00'" in sql          # lead.received_at
    assert any("uzyto daty szansy" in x for x in w)


def test_unknown_dictionary_values_are_kept_in_notes():
    rows = li.read_rows(_big_csv(**{"Źródło": "36", "Forma kontaktu": "Linked In",
                                    "Data archiwizacji": "02.03.2024",
                                    "Folder klienta": "B2B23"}))
    w = []
    sql = li.build(rows, fake_links(), [(1, "Natalia Test")], EXPORT, w.append)
    assert "Źródło (stary CRM): 36" in sql
    assert "Data archiwizacji (stary CRM): 02.03.2024" in sql
    assert "Folder klienta (stary CRM): B2B23" in sql
    assert not any("Linked In" in x for x in w)   # "Linked In" == "LinkedIn" (spacje)


def test_employee_matching_is_tolerant_but_unambiguous():
    emp = [(1, "Przemek Giemza"), (2, "Natalia Nowak"), (3, "Agnieszka Lasoń")]
    m = li.match_employee
    assert m("Natalia", emp) == [2] and m("Przemek", emp) == [1]
    assert m("Agnieszka Lasoń-Kurzela", emp) == [3]      # nazwisko dluzsze w pliku
    assert m("Agnieszka Lason", emp) == [3]              # bez ogonkow
    assert m("Ola", emp) == []
    assert len(m("Natalia", emp + [(4, "Natalia Inna")])) == 2   # niejednoznaczne


def test_small_warning_groups_are_listed_in_full():
    w = [f"#{i}: brak daty wplyniecia - uzyto daty szansy" for i in range(1, 30)]
    w += [f"#{i}: zrodlo '{i}' nie ma w opcjach - zapisane tylko w notatkach"
          for i in (5, 7)]
    out = li.group_warnings(w)
    assert out[0].startswith("29× brak daty wplyniecia") and "(np. #1, #2, #3)" in out[0]
    assert out[1:] == ["#5: zrodlo '5' nie ma w opcjach - zapisane tylko w notatkach",
                       "#7: zrodlo '7' nie ma w opcjach - zapisane tylko w notatkach"]
