#!/usr/bin/env python3
"""Dopisuje SZTUCZNE dane osobowe do zanonimizowanego CSV starego CRM.

Wypelnia (tylko gdy puste): Nazwa klienta, Organizacja, Kolumna1 (osoba),
Kolumna2 (telefon), Kolumna3 (e-mail). Reszta komorek bez zmian. Imiona/nazwy powtarzaja sie, ale e-mail, telefon i nazwa firmy sa
unikalne per osoba (numer w nazwie) - importer skleja osoby po e-mailu/telefonie,
wiec bez tego dochodzi do falszywych zlaczen. Dane sa
deterministyczne (--seed), e-maile w domenach example.*, telefony z zakresu
"600 000 xxx" - nie istnieja naprawde. ~6% wierszy powtarza osobe z wczesniejszego
wiersza (test sklejania powracajacych klientow), ~8% ma pusty telefon, ~8% pusty e-mail.

  python3 scripts/fake-crm-pii.py docs/crm/CRM_big-utf-8.csv docs/crm/CRM_big-fake-pii.csv
"""
import argparse
import csv
import io
import random
import unicodedata

FIRST = ["Anna", "Piotr", "Katarzyna", "Marek", "Agnieszka", "Tomasz", "Magdalena",
         "Krzysztof", "Joanna", "Michał", "Ewa", "Paweł", "Monika", "Jakub", "Dorota",
         "Łukasz", "Barbara", "Adam", "Natalia", "Rafał", "Karolina", "Grzegorz"]
LAST = ["Nowak", "Kowalski", "Wiśniewska", "Wójcik", "Kamińska", "Lewandowski",
        "Zielińska", "Szymański", "Woźniak", "Dąbrowska", "Kozłowski", "Jankowska",
        "Mazur", "Kwiatkowska", "Krawczyk", "Piotrowska", "Grabowski", "Pawłowska",
        "Michalski", "Król", "Wieczorek", "Jabłońska"]
CO1 = ["Alfa", "Beta", "Delta", "Orion", "Nova", "Polaris", "Vega", "Atlas", "Lumen",
       "Kuźnia", "Zenit", "Horyzont", "Bryza", "Mozaika", "Fala", "Cedr"]
CO2 = ["Systems", "Logistics", "Foods", "Energy", "Media", "Consulting", "Group",
       "Solutions", "Studio", "Trade", "Tech", "Partners"]
FORM = ["sp. z o.o.", "S.A.", "sp. k.", ""]


def ascii_(s):
    s = s.replace("ł", "l").replace("Ł", "L")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    text = open(a.src, "rb").read().decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    h = [c.replace("\n", " ").strip().lower() for c in rows[0]]
    i = {n: h.index(n) for n in ("nazwa klienta", "organizacja", "kolumna1", "kolumna2",
                                 "kolumna3", "b2b / b2c")}
    people, companies = [], []
    n_phone = 0
    for r in rows[1:]:
        if len(r) <= max(i.values()):
            continue
        b2b = r[i["b2b / b2c"]].strip().upper() == "B2B"
        if people and rnd.random() < 0.06:
            p = rnd.choice(people)          # powracajacy klient
        else:
            first, last = rnd.choice(FIRST), rnd.choice(LAST)
            n_phone += 1
            p = dict(name=f"{first} {last}", first=first, last=last, n=n_phone,
                     phone=f"+48 600 000 {n_phone % 1000:03d}" if n_phone < 1000 else
                     f"+48 600 {n_phone // 1000:03d} {n_phone % 1000:03d}")
            people.append(p)
        co = None
        if b2b:
            co = p.get("company") or (f"{rnd.choice(CO1)} {rnd.choice(CO2)} "
                                      f"{rnd.choice(FORM)}".strip() + f" {p['n']}")
            p["company"] = co
            domain = ascii_(co.split()[0]) + f"{p['n']}.example.com"
        else:
            domain = rnd.choice(["example.com", "example.org", "example.net"])
        mail = f"{ascii_(p['first'])}.{ascii_(p['last'])}.{p['n']}@{domain}"
        fill = {"nazwa klienta": co if b2b else p["name"], "organizacja": co or "",
                "kolumna1": p["name"], "kolumna2": p["phone"], "kolumna3": mail}
        if rnd.random() < 0.08:
            fill["kolumna2"] = ""
        if rnd.random() < 0.08:
            fill["kolumna3"] = ""
        for k, v in fill.items():
            if not r[i[k]].strip():
                r[i[k]] = v
    with open(a.dst, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f, lineterminator="\r\n").writerows(rows)
    print(f"zapisano {len(rows) - 1} wierszy -> {a.dst}")


if __name__ == "__main__":
    main()
