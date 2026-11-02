"""Usuwanie rekordow dodanych przez import (po zakresie ID z rejestru legacy.rows).

Do poprawek na UAT: ponowny import POMIJA wiersze, ktore juz sa w bazie
(klucz: rejestr legacy.rows), wiec zly import trzeba najpierw usunac. Kasuje tylko to, co
import tworzy: leady i szanse z legacy_id w zakresie, ich aktywnosci
(flow=import-crm-legacy), wpisy historii etapow (changed_by=import) oraz osoby
i firmy, do ktorych NIC innego nie jest juz podpiete. Wszystko w jednej
transakcji; domyslnie ROLLBACK (podglad).
"""
import re

import legacy_import as li
from legacy_import import SCHEMA, ident

JUNCTION_PREFIX = "_nc_m2m_"


def _refs(db):
    """(tabela-z-FK, kolumna, tabela-docelowa) dla wszystkich FK w schemacie."""
    strip = lambda x: x.split(".")[-1].strip('"')
    return [(strip(t), c, strip(r)) for t, c, r in db.run(
        f"SELECT c.conrelid::regclass::text, a.attname, c.confrelid::regclass::text "
        f"FROM pg_constraint c JOIN pg_attribute a ON a.attrelid=c.conrelid "
        f"AND a.attnum = ANY(c.conkey) JOIN pg_namespace n ON n.oid=c.connamespace "
        f"WHERE c.contype='f' AND n.nspname='{SCHEMA}'", tuples=True)]


def _junction(links, name):
    L = links[name]
    if L["kind"] != "junction":
        raise li.LegacyError(f"{name}: oczekiwano tabeli laczacej (FK nieobslugiwany).")
    return f"{SCHEMA}.{ident(L['table'])}", ident(L["owner"]), ident(L["other"])


def parse_range(text):
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", text.strip())
    if not m:
        raise li.LegacyError("Zakres ID: np. 1704-1713 albo 1704.")
    lo = int(m[1]); hi = int(m[2] or m[1])
    if lo > hi:
        raise li.LegacyError("Zakres ID: poczatek wiekszy od konca.")
    return lo, hi


def run_cleanup(db, schema_map, lo, hi, apply=False):
    links = li.discover(db, schema_map)
    refs = _refs(db)
    s = SCHEMA
    out = [f"l_ids := array(SELECT lead_id FROM {li.REGISTRY} WHERE export_id BETWEEN {lo} AND {hi} AND lead_id IS NOT NULL);",
           f"o_ids := array(SELECT opportunity_id FROM {li.REGISTRY} WHERE export_id BETWEEN {lo} AND {hi} AND opportunity_id IS NOT NULL);"]
    t, o, c = _junction(links, "lead_activities")
    out.append(f"a_ids := array(SELECT id FROM {s}.activities WHERE flow = 'import-crm-legacy' "
               f"AND id IN (SELECT {c} FROM {t} WHERE {o} = ANY(l_ids)));")
    t, o, c = _junction(links, "history_opp")
    out.append(f"h_ids := array(SELECT id FROM {s}.sale_opportunity_stage_history "
               f"WHERE changed_by = 'import' AND id IN (SELECT {o} FROM {t} WHERE {c} = ANY(o_ids)));")

    def collect(var, pairs):
        parts = []
        for name, ids in pairs:
            t, o, c = _junction(links, name)
            parts.append(f"SELECT {c} FROM {t} WHERE {o} = ANY({ids})")
        return f"{var} := array({' UNION '.join(parts)});"
    out.append(collect("p_ids", [("lead_persons", "l_ids"), ("lead_primary_person", "l_ids"),
                                 ("opp_person", "o_ids")]))
    out.append(collect("c_ids", [("lead_company", "l_ids"), ("opp_company", "o_ids")]))

    def unlink_and_delete(table, ids, label):
        for rt, col, ref in refs:
            if ref != table:
                continue
            if rt.startswith(JUNCTION_PREFIX):
                out.append(f"DELETE FROM {s}.{ident(rt)} WHERE {ident(col)} = ANY({ids});")
            else:
                out.append(f"IF EXISTS (SELECT 1 FROM {s}.{ident(rt)} WHERE {ident(col)} = ANY({ids})) "
                           f"THEN RAISE EXCEPTION 'Tabela {rt} wskazuje na {table} - przerwano'; END IF;")
        out.append(f"DELETE FROM {s}.{table} WHERE id = ANY({ids}); "
                   f"GET DIAGNOSTICS n = ROW_COUNT; RAISE NOTICE 'deleted {label}=%', n;")

    unlink_and_delete("sale_opportunity_stage_history", "h_ids", "history")
    unlink_and_delete("activities", "a_ids", "activities")
    unlink_and_delete("sale_opportunities", "o_ids", "opportunities")
    unlink_and_delete("leads", "l_ids", "leads")
    # numery z rejestru zwalniamy (import poprawionego pliku bierze je od nowa)
    out.append(f"DELETE FROM {li.REGISTRY} WHERE export_id BETWEEN {lo} AND {hi} AND source = 'import';")

    # osoby: tylko te, do ktorych nic poza ich wlasnym linkiem do firmy nie prowadzi
    own = links["person_company"]["table"]
    for table, cand, label, skip in (("persons", "p_ids", "persons", own),
                                     ("companies", "c_ids", "companies", None)):
        conds = [f"NOT EXISTS (SELECT 1 FROM {s}.{ident(rt)} WHERE {ident(col)} = x.id)"
                 for rt, col, ref in refs if ref == table and rt != skip]
        out.append(f"orphans := array(SELECT x.id FROM {s}.{table} x WHERE x.id = ANY({cand}) "
                   f"AND {' AND '.join(conds) or 'true'});")
        if skip:
            for rt, col, ref in refs:
                if ref == table and rt == skip:
                    out.append(f"DELETE FROM {s}.{ident(rt)} WHERE {ident(col)} = ANY(orphans);")
        out.append(f"DELETE FROM {s}.{table} WHERE id = ANY(orphans); "
                   f"GET DIAGNOSTICS n = ROW_COUNT; RAISE NOTICE 'deleted {label}=%', n;")
        out.append(f"RAISE NOTICE 'kept {label}=%', cardinality({cand}) - n;")

    sql = ("BEGIN;\nDO $cleanup$\nDECLARE l_ids bigint[]; o_ids bigint[]; a_ids bigint[]; "
           "h_ids bigint[]; p_ids bigint[]; c_ids bigint[]; orphans bigint[]; n int;\nBEGIN\n"
           + "\n".join(out) + f"\nEND $cleanup$;\n{'COMMIT' if apply else 'ROLLBACK'};\n")
    res = db.run(sql)
    counts = {k: int(v) for k, v in re.findall(r"(deleted \w+|kept \w+)=(\d+)", res)}
    if not counts:
        raise li.LegacyError(f"Brak podsumowania z bazy: {res[-300:]}")
    return dict(applied=apply, range=[lo, hi], counts=counts)
