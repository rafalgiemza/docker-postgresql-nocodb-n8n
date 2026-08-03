#!/usr/bin/env python3
"""
CRM pipeline data generator for `Statusy_z_CRM.xlsx`.

Generates a realistic, internally consistent sales pipeline history:
every row walks a lead through the funnel stage by stage, so the date
columns, the stage (`Etap`), the state (`Stan`) and the reason columns
always agree with each other.

Key modelling decisions (all tunable in the CONFIG section):
  * lead volume grows year over year and follows a monthly seasonality curve
  * only deals from the last OPEN_WINDOW_DAYS may still be open; anything
    older is either won, lost or disqualified
  * business dates never land on weekends or Polish public holidays
  * sales reps have hire/leave dates, so old rows are not assigned to
    someone who joined in 2023
  * deal values follow a lognormal distribution, inflated over time

Usage:
    python generate_crm_data.py --rows 1600 --seed 42
    python generate_crm_data.py --template in.xlsx --output out.xlsx --keep-samples

Requires: openpyxl, faker
"""

from __future__ import annotations

import argparse
import random
import unicodedata
from copy import copy
from datetime import date, datetime, time, timedelta

from faker import Faker
from openpyxl import load_workbook

# ---------------------------------------------------------------------------
# CONFIG — dictionaries. Replace these with the real CRM dictionaries.
# ---------------------------------------------------------------------------

SHEET_NAME = "Arkusz1"
HEADER_ROW = 1
FIRST_DATA_ROW = 2
STYLE_TEMPLATE_ROW = 2  # existing sample row used as the formatting template

# Deals older than this are never left in an "open" state.
OPEN_WINDOW_DAYS = 120

# If True, a lost deal keeps the last stage it reached in `Etap`
# (the loss is then only visible through `Data utracenia` / `Powód utraty`).
# If False, `Etap` is explicitly set to LOST_STAGE.
LOST_KEEPS_LAST_STAGE = False
LOST_STAGE = "utracona"
DISQUALIFIED_STAGE = "brak kwalifikacji"

# (name, hired, left) — None means "still employed"
SALES_REPS = [
    ("Marek", date(2009, 1, 1), date(2016, 6, 30)),
    ("Anna", date(2009, 1, 1), None),
    ("Przemek", date(2013, 3, 1), None),
    ("Kasia", date(2015, 9, 1), date(2022, 4, 30)),
    ("Tomek", date(2018, 2, 1), None),
    ("Ola", date(2021, 6, 1), None),
    ("Bartek", date(2023, 10, 1), None),
]

# Lead sources with popularity weight per era. Weights are (pre-2015,
# 2015-2019, 2020+) so channel mix drifts over the 15-year span.
SOURCES = {
    "Google": (40, 35, 30),
    "Polecenie": (25, 20, 18),
    "Strona www": (12, 12, 12),
    "Cold mail": (10, 8, 6),
    "Targi": (8, 6, 3),
    "Facebook": (4, 8, 6),
    "LinkedIn": (1, 8, 15),
    "Kampania Ads": (0, 3, 7),
    "Webinar": (0, 0, 3),
}

CONTACT_FORMS = {
    "Bookings": 22,
    "Formularz WWW": 28,
    "Telefon": 20,
    "E-mail": 20,
    "Czat": 6,
    "Spotkanie": 4,
}

INDUSTRIES = {
    "Software Development": 14,
    "E-commerce": 13,
    "Produkcja": 12,
    "Budownictwo": 10,
    "Logistyka": 9,
    "Handel detaliczny": 9,
    "Usługi finansowe": 7,
    "Medycyna": 7,
    "Edukacja": 6,
    "HoReCa": 5,
    "Nieruchomości": 4,
    "Marketing": 4,
}

# Lead quality by source: probability of MQL / SQL / disqualified.
QUALIFICATION_BY_SOURCE = {
    "Polecenie": (0.30, 0.62, 0.08),
    "Targi": (0.38, 0.47, 0.15),
    "LinkedIn": (0.40, 0.42, 0.18),
    "Webinar": (0.42, 0.40, 0.18),
    "Google": (0.42, 0.36, 0.22),
    "Strona www": (0.44, 0.34, 0.22),
    "Kampania Ads": (0.40, 0.30, 0.30),
    "Facebook": (0.38, 0.24, 0.38),
    "Cold mail": (0.34, 0.22, 0.44),
}
DEFAULT_QUALIFICATION = (0.40, 0.35, 0.25)

DISQUALIFICATION_REASONS = {
    "Brak kontaktu": 26,
    "Poza obszarem działania": 14,
    "Brak budżetu": 16,
    "Spam / bot": 8,
    "Szuka pracy": 7,
    "Oferta konkurencji / handlowiec": 6,
    "Nie nasza usługa": 13,
    "Duplikat": 10,
}

LOSS_REASONS = {
    "Cena": 24,
    "Wybrał konkurencję": 20,
    "Brak decyzji / cisza": 18,
    "Brak budżetu": 12,
    "Odłożone w czasie": 10,
    "Realizacja wewnętrzna": 7,
    "Za długi termin realizacji": 5,
    "Zmiana potrzeb": 4,
}

PLANNED_ACTIONS = {
    "Telefon kontrolny": 30,
    "Follow-up mailowy": 26,
    "Spotkanie online": 16,
    "Przygotowanie oferty": 12,
    "Wysyłka umowy": 8,
    "Spotkanie u klienta": 8,
}

DEAL_LABELS = {
    "Nowy klient": 46,
    "Upsell": 16,
    "Odnowienie": 14,
    "Projekt jednorazowy": 12,
    "Abonament": 8,
    "Pilne": 4,
}

NOTE_TEMPLATES = [
    "Klient prosi o kontakt po {month}.",
    "Decyzję podejmuje zarząd, termin nieznany.",
    "Budżet do potwierdzenia w kolejnym kwartale.",
    "Porównuje nas z dwoma innymi dostawcami.",
    "Wysłano dodatkowe materiały i case study.",
    "Kontakt tylko mailowy, nie odbiera telefonu.",
    "Poleceni przez dotychczasowego klienta.",
    "Wymagana integracja z obecnym systemem.",
    "Prosi o wersję oferty z rozłożeniem na raty.",
    "Termin realizacji kluczowy, pyta o dostępność zespołu.",
]
MONTHS_PL = [
    "styczniu", "lutym", "marcu", "kwietniu", "maju", "czerwcu",
    "lipcu", "sierpniu", "wrześniu", "październiku", "listopadzie", "grudniu",
]

B2C_EMAIL_DOMAINS = ["gmail.com", "wp.pl", "o2.pl", "interia.pl", "onet.pl"]

# Share of B2B leads (the rest are B2C).
B2B_SHARE = 0.62

# Monthly seasonality multipliers (index 0 = January).
MONTH_SEASONALITY = [1.15, 1.10, 1.15, 1.05, 1.00, 0.90,
                     0.65, 0.60, 1.20, 1.20, 1.10, 0.70]

# Yearly lead volume growth (compounding, applied from the first year).
YEARLY_GROWTH = 0.11

# ---------------------------------------------------------------------------
# CONFIG — funnel transition probabilities.
# Probability of moving from one stage to the next, given the deal got here.
# `_recent_bonus` lifts conversion in later years (process maturity).
# ---------------------------------------------------------------------------

STAGE_FLOW = [
    # (date column key, stage label, probability of reaching it)
    ("needs_analysis", "badanie potrzeb", 0.88),
    ("demo", "DEMO", 0.74),
    ("offer_sent", "oferta wysłana", 0.80),
    ("offer_discussed", "omówienie oferty", 0.78),
    ("contract_sent", "umowa wysłana", 0.55),
    ("contract_signed", "umowa podpisana", 0.72),
]

# Typical business-day gaps between consecutive funnel steps (min, mode, max).
STAGE_GAPS = {
    "created": (0, 1, 3),
    "opportunity": (0, 0, 2),
    "needs_analysis": (0, 1, 5),
    "demo": (1, 3, 12),
    "offer_sent": (1, 3, 10),
    "offer_discussed": (0, 2, 8),
    "contract_sent": (1, 4, 15),
    "contract_signed": (1, 5, 25),
}

# Deal value (PLN) lognormal parameters per segment, in 2011 money.
VALUE_PARAMS = {"B2B": (9.6, 0.75), "B2C": (8.3, 0.6)}
VALUE_INFLATION = 0.045  # per year


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------

def easter_sunday(year: int) -> date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1)


_HOLIDAY_CACHE: dict[int, set[date]] = {}


def polish_holidays(year: int) -> set[date]:
    """Public holidays in Poland for a given year."""
    if year in _HOLIDAY_CACHE:
        return _HOLIDAY_CACHE[year]
    easter = easter_sunday(year)
    days = {
        date(year, 1, 1), date(year, 1, 6), date(year, 5, 1), date(year, 5, 3),
        date(year, 8, 15), date(year, 11, 1), date(year, 11, 11),
        date(year, 12, 25), date(year, 12, 26),
        easter, easter + timedelta(days=1),          # Easter Monday
        easter + timedelta(days=49),                 # Pentecost
        easter + timedelta(days=60),                 # Corpus Christi
    }
    _HOLIDAY_CACHE[year] = days
    return days


def is_business_day(day: date) -> bool:
    return day.weekday() < 5 and day not in polish_holidays(day.year)


def next_business_day(day: date) -> date:
    while not is_business_day(day):
        day += timedelta(days=1)
    return day


def add_business_days(start: date, days: int) -> date:
    """Add N business days, always returning a business day."""
    current = next_business_day(start)
    for _ in range(days):
        current = next_business_day(current + timedelta(days=1))
    return current


# ---------------------------------------------------------------------------
# Random helpers
# ---------------------------------------------------------------------------

def weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def triangular_int(rng: random.Random, bounds: tuple[int, int, int]) -> int:
    low, mode, high = bounds
    return int(round(rng.triangular(low, high, mode)))


def slugify(text: str) -> str:
    """ASCII slug used for e-mail addresses and folder names."""
    normalized = unicodedata.normalize("NFKD", text.replace("ł", "l").replace("Ł", "L"))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = [ch.lower() if ch.isalnum() else "-" for ch in ascii_text]
    slug = "".join(cleaned)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def source_weights_for(year: int) -> dict[str, float]:
    era = 0 if year < 2015 else (1 if year < 2020 else 2)
    return {name: w[era] for name, w in SOURCES.items() if w[era] > 0}


def maturity_bonus(day: date, start_year: int) -> float:
    """Conversion improves slightly every year (better process, better leads)."""
    return min(0.06, 0.005 * (day.year - start_year))


# ---------------------------------------------------------------------------
# Volume model
# ---------------------------------------------------------------------------

def build_inflow_dates(rng: random.Random, total_rows: int,
                       start: date, end: date) -> list[date]:
    """Distribute `total_rows` lead inflow dates over [start, end]."""
    # Build a month-by-month weight curve: growth * seasonality.
    months: list[tuple[int, int]] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        months.append((cursor.year, cursor.month))
        cursor = date(cursor.year + (cursor.month == 12),
                      cursor.month % 12 + 1, 1)

    weights = []
    for year, month in months:
        growth = (1 + YEARLY_GROWTH) ** (year - start.year)
        weights.append(growth * MONTH_SEASONALITY[month - 1])

    picks = rng.choices(range(len(months)), weights=weights, k=total_rows)

    dates: list[date] = []
    for index in picks:
        year, month = months[index]
        last_day = (date(year + (month == 12), month % 12 + 1, 1)
                    - timedelta(days=1)).day
        day = rng.randint(1, last_day)
        candidate = date(year, month, day)
        candidate = min(max(candidate, start), end)
        dates.append(candidate)

    dates.sort()
    return dates


def inflow_time(rng: random.Random, day: date) -> time:
    """Business-hours-weighted inflow time (leads still trickle in at night)."""
    if is_business_day(day) and rng.random() < 0.88:
        hour = rng.choices(
            [8, 9, 10, 11, 12, 13, 14, 15, 16, 17],
            weights=[5, 12, 15, 14, 10, 9, 11, 10, 8, 6], k=1)[0]
    else:
        hour = rng.choices(
            list(range(0, 24)),
            weights=[1, 1, 1, 1, 1, 2, 3, 4, 5, 6, 6, 6,
                     5, 5, 5, 5, 5, 6, 7, 8, 8, 7, 4, 2], k=1)[0]
    return time(hour, rng.randint(0, 59))


# ---------------------------------------------------------------------------
# Row generation
# ---------------------------------------------------------------------------

def generate_row(rng: random.Random, fake: Faker, lead_id: int,
                 inflow: date, today: date, start_year: int) -> dict:
    """Simulate one lead through the funnel and return a column->value map."""
    row: dict[str, object] = {}

    segment = "B2B" if rng.random() < B2B_SHARE else "B2C"
    source = weighted_choice(rng, source_weights_for(inflow.year))
    contact_form = weighted_choice(rng, CONTACT_FORMS)

    # --- identity -----------------------------------------------------------
    person = fake.name()
    if segment == "B2B":
        company = fake.company()
        client_name = company
        organization = company
        contact_person = person
        domain = f"{slugify(company)[:22]}.pl"
        email = f"{slugify(person).replace('-', '.')}@{domain}"
    else:
        client_name = person
        organization = None
        contact_person = person
        email = (f"{slugify(person).replace('-', '.')}"
                 f"{rng.choice(['', str(rng.randint(1, 99))])}"
                 f"@{rng.choice(B2C_EMAIL_DOMAINS)}")

    rep_pool = [name for name, hired, left in SALES_REPS
                if hired <= inflow and (left is None or left >= inflow)]
    rep = rng.choice(rep_pool) if rep_pool else SALES_REPS[1][0]

    row.update({
        "ID": lead_id,
        "Nazwa klienta": client_name,
        "Organizacja": organization,
        "B2B / B2C": segment,
        "Handlowiec\n": rep,
        "Branża": weighted_choice(rng, INDUSTRIES),
        "Źródło": source,
        "Forma \nkontaktu": contact_form,
        "Osoba kontaktowa": contact_person,
        "Nr telefonu": f"+48 {rng.randint(500, 899)} {rng.randint(100, 999)} "
                       f"{rng.randint(100, 999)}",
        "E.mail": email,
        "Data \nwpłynięcia": inflow,
        "Godzina \nwpłynięcia": inflow_time(rng, inflow),
    })

    # --- qualification ------------------------------------------------------
    p_mql, p_sql, p_bad = QUALIFICATION_BY_SOURCE.get(source, DEFAULT_QUALIFICATION)
    qualification = rng.choices(["MQL", "SQL", "Brak kwalifikacji"],
                                weights=[p_mql, p_sql, p_bad], k=1)[0]
    row["Kwalifikacja lead'a"] = qualification

    if qualification == "Brak kwalifikacji":
        # Disqualified leads never become clients; they get archived instead.
        row["Powód braku kwalifikacji lead'a"] = weighted_choice(
            rng, DISQUALIFICATION_REASONS)
        archived = add_business_days(inflow, rng.randint(0, 6))
        if archived <= today:
            row["Data archiwizacji"] = archived
        row["Etap"] = DISQUALIFIED_STAGE
        row["Stan"] = "zamknięta"
        return row

    # --- client + opportunity ----------------------------------------------
    created = add_business_days(inflow, triangular_int(rng, STAGE_GAPS["created"]))
    if created > today:
        # Lead arrived too recently to have been processed yet.
        row["Etap"] = "nowy lead"
        row["Stan"] = "otwarta"
        row["Data planowanego działania"] = add_business_days(today, rng.randint(0, 3))
        row["Planowane działanie"] = weighted_choice(rng, PLANNED_ACTIONS)
        return row

    opportunity = min(
        add_business_days(created, triangular_int(rng, STAGE_GAPS["opportunity"])),
        today)
    row["Data utworzenia klienta"] = created
    row["Data szansy sprzedaży"] = opportunity
    row["Folder klienta"] = f"{slugify(client_name)[:30]}-{lead_id}"

    # --- funnel walk --------------------------------------------------------
    bonus = maturity_bonus(inflow, start_year)
    if qualification == "SQL":
        bonus += 0.04

    cursor = opportunity
    reached_stage = "nowy lead"
    dropped = False

    stage_columns = {
        "needs_analysis": "Data badania potrzeb",
        "demo": "Data \nDEMO",
        "offer_sent": "Data wysłania oferty",
        "offer_discussed": "Data omówienia oferty",
        "contract_sent": "Data wysłania umowy",
        "contract_signed": "Data podpisania umowy",
    }

    for key, label, base_probability in STAGE_FLOW:
        if rng.random() > min(0.97, base_probability + bonus):
            dropped = True
            break
        cursor = add_business_days(cursor, triangular_int(rng, STAGE_GAPS[key]))
        if cursor > today:
            # The next step would land in the future - keep the deal at the
            # stage it has actually reached.
            dropped = True
            cursor = min(cursor, today)
            break
        row[stage_columns[key]] = cursor
        reached_stage = label

    won = not dropped and reached_stage == "umowa podpisana"

    # --- deal value ---------------------------------------------------------
    mu, sigma = VALUE_PARAMS[segment]
    inflated = mu + VALUE_INFLATION * (inflow.year - start_year)
    value = rng.lognormvariate(inflated, sigma)
    row["Szansa sprzedaży  \nWartość"] = round(value / 50) * 50.0
    row["Szansa sprzedaży . Etykieta"] = weighted_choice(rng, DEAL_LABELS)

    if rng.random() < 0.28:
        row["Notatki"] = rng.choice(NOTE_TEMPLATES).format(
            month=rng.choice(MONTHS_PL))

    # --- closing ------------------------------------------------------------
    if won:
        row["Etap"] = "umowa podpisana"
        row["Stan"] = "zamknięta"
        signed = row[stage_columns["contract_signed"]]
        row["Spr. ID"] = f"SPR/{signed.year}/{lead_id:05d}"
        return row

    age_days = (today - inflow).days
    still_open = age_days <= OPEN_WINDOW_DAYS and rng.random() < 0.75

    if still_open:
        row["Etap"] = reached_stage
        row["Stan"] = "otwarta"
        planned = add_business_days(max(cursor, today), rng.randint(1, 21))
        row["Data planowanego działania"] = planned
        row["Planowane działanie"] = weighted_choice(rng, PLANNED_ACTIONS)
        return row

    lost_on = add_business_days(cursor, rng.randint(2, 30))
    lost_on = min(lost_on, today)
    row["Data \nutracenia"] = lost_on
    row["Powód utraty szansy"] = weighted_choice(rng, LOSS_REASONS)
    row["Etap"] = reached_stage if LOST_KEEPS_LAST_STAGE else LOST_STAGE
    row["Stan"] = "zamknięta"
    if rng.random() < 0.45:
        row["Data archiwizacji"] = add_business_days(lost_on, rng.randint(1, 20))
        if row["Data archiwizacji"] > today:
            del row["Data archiwizacji"]
    return row


# ---------------------------------------------------------------------------
# Workbook writing
# ---------------------------------------------------------------------------

def write_workbook(rows: list[dict], template_path: str, output_path: str,
                   keep_samples: bool) -> None:
    workbook = load_workbook(template_path)
    sheet = workbook[SHEET_NAME]

    headers = {}
    for cell in sheet[HEADER_ROW]:
        if cell.value is not None:
            headers[str(cell.value)] = cell.column

    # Capture the formatting of the sample row before it is removed.
    style_template = {cell.column: copy(cell._style)
                      for cell in sheet[STYLE_TEMPLATE_ROW]}

    start_row = FIRST_DATA_ROW
    if keep_samples:
        start_row = sheet.max_row + 1
    elif sheet.max_row >= FIRST_DATA_ROW:
        sheet.delete_rows(FIRST_DATA_ROW, sheet.max_row - FIRST_DATA_ROW + 1)

    unknown = {key for row in rows for key in row} - set(headers)
    if unknown:
        raise KeyError(f"Columns not present in the template header: {unknown}")

    for offset, row in enumerate(rows):
        excel_row = start_row + offset
        for column_index in range(1, sheet.max_column + 1):
            cell = sheet.cell(row=excel_row, column=column_index)
            if column_index in style_template:
                cell._style = copy(style_template[column_index])
        for header, value in row.items():
            if value is None:
                continue
            cell = sheet.cell(row=excel_row, column=headers[header])
            cell.value = (datetime(value.year, value.month, value.day)
                          if isinstance(value, date) and not isinstance(value, datetime)
                          else value)

    workbook.save(output_path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 15 years of CRM pipeline data.")
    parser.add_argument("--template", default="Statusy_z_CRM.xlsx",
                        help="source .xlsx whose header and styles are reused")
    parser.add_argument("--output", default="Statusy_z_CRM_filled.xlsx")
    parser.add_argument("--rows", type=int, default=1600)
    parser.add_argument("--years", type=float, default=15.0)
    parser.add_argument("--end-date", default=None,
                        help="last inflow date, YYYY-MM-DD (default: today)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--start-id", type=int, default=1)
    parser.add_argument("--keep-samples", action="store_true",
                        help="append below the existing rows instead of replacing them")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    fake = Faker("pl_PL")
    Faker.seed(args.seed)

    today = (date.fromisoformat(args.end_date) if args.end_date else date.today())
    start = today - timedelta(days=int(args.years * 365.25))

    inflow_dates = build_inflow_dates(rng, args.rows, start, today)
    rows = [generate_row(rng, fake, args.start_id + i, day, today, start.year)
            for i, day in enumerate(inflow_dates)]

    write_workbook(rows, args.template, args.output, args.keep_samples)

    won = sum(1 for r in rows if r.get("Etap") == "umowa podpisana")
    lost = sum(1 for r in rows if r.get("Data \nutracenia"))
    disqualified = sum(1 for r in rows if r.get("Etap") == DISQUALIFIED_STAGE)
    open_deals = sum(1 for r in rows if r.get("Stan") == "otwarta")
    print(f"{len(rows)} rows written to {args.output}")
    print(f"  {start} -> {today}")
    print(f"  won: {won} ({won / len(rows):.1%}) | lost: {lost} | "
          f"disqualified: {disqualified} | open: {open_deals}")


if __name__ == "__main__":
    main()
