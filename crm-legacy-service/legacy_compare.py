"""Porownanie pliku wejsciowego (stary CRM) z eksportem - test pelnego obiegu.

Wiersze laczone po ID, komorki porownywane po znaczeniu (data = ta sama data,
kwota = ta sama kwota, tekst bez roznic w wielkosci liter i spacjach), wiec
rozne zapisy tej samej wartosci ("3,900.00 PLN" / "3900") nie sa roznica.
Raport: ID tylko w jednym pliku oraz liczba roznic w kazdej kolumnie z
przykladami (ID, wartosc z pliku, wartosc z eksportu).
"""
import re
from datetime import date, datetime

import legacy_import as li
from legacy_import import C

DATE_KEYS = ("received_d", "client_created", "opp_created", "needs", "demo",
             "offer_sent", "offer_discussed", "contract_sent", "contract_signed",
             "lost_d")
LOOSE_KEYS = ("source", "channel", "industry", "qualification")  # 'Linked In' = 'LinkedIn'
SKIP_KEYS = ("id",)


def norm(key, v, export_date):
    v = (v or "").strip()
    if not v:
        return ""
    if key in DATE_KEYS:
        d = li.parse_date(v, export_date, lambda w: None, "")
        return d.isoformat() if d else v
    if key == "received_t":
        for fmt in ("%I:%M:%S %p", "%H:%M:%S", "%H:%M", "%I:%M %p"):
            try:
                return datetime.strptime(v, fmt).strftime("%H:%M:%S")
            except ValueError:
                continue
        return v
    if key == "value":
        return li.money(v) or v
    if key in LOOSE_KEYS:
        return re.sub(r"[\s.\-]", "", v).lower()
    return re.sub(r"\s+", " ", v).casefold()


def compare(original_text, exported_text, export_date=date(2026, 10, 30), examples=3):
    a = {int(r[C["id"]]): r for r in li.read_rows(original_text)}
    b = {int(r[C["id"]]): r for r in li.read_rows(exported_text)}
    diffs = {k: [] for k in C if k not in SKIP_KEYS}
    identical = 0
    for i in sorted(set(a) & set(b), reverse=True):
        same = True
        for k in diffs:
            x, y = norm(k, a[i][C[k]], export_date), norm(k, b[i][C[k]], export_date)
            if x != y:
                diffs[k].append((i, a[i][C[k]], b[i][C[k]]))
                same = False
        identical += same
    return dict(
        rows_original=len(a), rows_export=len(b), identical=identical,
        only_original=sorted(set(a) - set(b), reverse=True),
        only_export=sorted(set(b) - set(a), reverse=True),
        diffs={k: v for k, v in diffs.items() if v}, examples=examples)


def render(res):
    out = [f"Wiersze: plik {res['rows_original']}, eksport {res['rows_export']}, "
           f"identyczne co do znaczenia: {res['identical']}"]
    for label, key in (("Tylko w pliku", "only_original"), ("Tylko w eksporcie", "only_export")):
        if res[key]:
            out.append(f"{label} ({len(res[key])}): " + ", ".join(f"#{i}" for i in res[key][:50]))
    for k, items in sorted(res["diffs"].items(), key=lambda kv: -len(kv[1])):
        ex = "; ".join(f"#{i}: {o!r} -> {e!r}" for i, o, e in items[:res["examples"]])
        out.append(f"{k}: {len(items)} różnic ({ex})")
    if not res["diffs"] and not res["only_original"] and not res["only_export"]:
        out.append("Brak różnic.")
    return "\n".join(out)
