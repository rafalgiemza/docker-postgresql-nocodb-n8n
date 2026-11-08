"""Test narzedzia do porownania pliku wejsciowego z eksportem."""
import legacy_compare as lc

HEAD = ("ID,B2B / B2C,Źródło,Data wpłynięcia,Data szansy sprzedaży,Data podpisania umowy,"
        "Szansa sprzedaży Wartość\n")


def test_same_meaning_in_different_notation_is_not_a_difference():
    a = HEAD + '5,B2C,Linked In,03/07/2026,3/7/2026,"1/2/2026","3,900.00 PLN"\n'
    b = HEAD + '5,B2C,LinkedIn,3/7/2026,3/7/2026,1/2/2026,3900\n'
    res = lc.compare(a, b)
    assert res["identical"] == 1 and not res["diffs"]


def test_reports_differences_and_missing_rows():
    a = HEAD + "5,B2C,Google,3/7/2026,3/7/2026,1/2/2026,\n9,B2C,,,3/7/2026,,\n"
    b = HEAD + "5,B2C,Google,3/7/2026,3/7/2026,1/9/2026,\n"
    res = lc.compare(a, b)
    assert res["only_original"] == [9] and res["identical"] == 0
    assert list(res["diffs"]) == ["contract_signed"]
    assert "1 różnic" in lc.render(res) and "#9" in lc.render(res)
