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
