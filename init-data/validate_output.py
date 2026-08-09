#!/usr/bin/env python3
"""Sanity checks for the generated CRM file: date ordering, stage/state
consistency and column completeness. Exits non-zero on any violation."""

import sys
from datetime import datetime

import pandas as pd

PATH = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/outputs/Statusy_z_CRM_filled.xlsx"
df = pd.read_excel(PATH, sheet_name="Arkusz1")

DATE_CHAIN = [
    "Data \nwpłynięcia", "Data utworzenia klienta", "Data szansy sprzedaży",
    "Data badania potrzeb", "Data \nDEMO", "Data wysłania oferty",
    "Data omówienia oferty", "Data wysłania umowy", "Data podpisania umowy",
]

problems = []

# 1. Date chain must be non-decreasing wherever both dates exist.
for i in range(len(DATE_CHAIN) - 1):
    a, b = DATE_CHAIN[i], DATE_CHAIN[i + 1]
    mask = df[a].notna() & df[b].notna() & (df[b] < df[a])
    if mask.any():
        problems.append(f"{b} earlier than {a}: {int(mask.sum())} rows")

# 2. No gaps in the funnel (a stage date requires every previous one).
for i in range(1, len(DATE_CHAIN)):
    gap = df[DATE_CHAIN[i]].notna() & df[DATE_CHAIN[i - 1]].isna()
    if gap.any():
        problems.append(f"{DATE_CHAIN[i]} set without {DATE_CHAIN[i-1]}: {int(gap.sum())}")

# 3. Won deals: signed date present, state closed, sale ID present.
won = df["Etap"] == "umowa podpisana"
if (df.loc[won, "Data podpisania umowy"].isna()).any():
    problems.append("won deal without signature date")
if (df.loc[won, "Stan"] != "zamknięta").any():
    problems.append("won deal not closed")
if (df.loc[won, "Spr. ID"].isna()).any():
    problems.append("won deal without Spr. ID")
if (df.loc[won, "Data \nutracenia"].notna()).any():
    problems.append("won deal with a loss date")

# 4. Lost deals must carry both loss date and reason.
lost_date = df["Data \nutracenia"].notna()
lost_reason = df["Powód utraty szansy"].notna()
if (lost_date != lost_reason).any():
    problems.append("loss date and loss reason out of sync")

# 5. Disqualified leads never become clients.
dq = df["Kwalifikacja lead'a"] == "Brak kwalifikacji"
if df.loc[dq, "Data utworzenia klienta"].notna().any():
    problems.append("disqualified lead with a client creation date")
if (df.loc[dq, "Powód braku kwalifikacji lead'a"].isna()).any():
    problems.append("disqualified lead without a reason")

# 6. Open deals: state open, planned action in the future, not won/lost.
open_deals = df["Stan"] == "otwarta"
if df.loc[open_deals, "Data planowanego działania"].isna().any():
    problems.append("open deal without a planned action date")
if df.loc[open_deals, "Data \nutracenia"].notna().any():
    problems.append("open deal with a loss date")

# 7. Nothing in the future, IDs unique and ordered by inflow date.
today = datetime.combine(df["Data \nwpłynięcia"].max().date(), datetime.min.time())
for column in DATE_CHAIN + ["Data \nutracenia", "Data archiwizacji"]:
    if (df[column] > today).any():
        problems.append(f"{column} in the future")
if df["ID"].duplicated().any():
    problems.append("duplicated ID")
if not df["ID"].is_monotonic_increasing or not df["Data \nwpłynięcia"].is_monotonic_increasing:
    problems.append("ID / inflow date not chronological")

# 8. B2C rows have no organisation, B2B rows do.
b2c = df["B2B / B2C"] == "B2C"
if df.loc[b2c, "Organizacja"].notna().any():
    problems.append("B2C row with an organisation")
if df.loc[~b2c, "Organizacja"].isna().any():
    problems.append("B2B row without an organisation")

print(f"rows: {len(df)}  columns: {len(df.columns)}")
print(df["Etap"].value_counts().to_string())
print("\nleads per year:")
print(df.groupby(df["Data \nwpłynięcia"].dt.year).size().to_string())
print(f"\nvalue: median {df['Szansa sprzedaży  \nWartość'].median():,.0f} PLN  "
      f"max {df['Szansa sprzedaży  \nWartość'].max():,.0f} PLN")
print(f"won pipeline value: {df.loc[won, 'Szansa sprzedaży  \nWartość'].sum():,.0f} PLN")

if problems:
    print("\nFAILED:")
    for problem in problems:
        print(" -", problem)
    sys.exit(1)
print("\nAll consistency checks passed.")
