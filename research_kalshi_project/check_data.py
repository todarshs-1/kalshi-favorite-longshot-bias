"""
check_data.py

Quick sanity check on kalshi_combined_settled.csv using pandas.
Confirms implied_probability and result columns actually have real data
before we build any analysis on top of them.
"""

import pandas as pd

df = pd.read_csv("kalshi_combined_settled.csv", encoding="latin-1")

print(f"Total rows: {len(df)}\n")

print("--- implied_probability ---")
print(df["implied_probability"].describe())  # count, mean, min, max, etc.
print(f"Missing/blank values: {df['implied_probability'].isna().sum()}\n")

print("--- result ---")
print(df["result"].value_counts(dropna=False))  # counts of each unique value, including blanks

print("\n--- First 5 rows, key columns only ---")
print(df[["series", "ticker", "implied_probability", "result"]].head())

print("\n--- Checking if implied_probability=0.5 correlates with zero volume ---")
stuck_at_half = df[df["implied_probability"] == 0.5]
not_stuck = df[df["implied_probability"] != 0.5]

print(f"Rows stuck at exactly 0.5: {len(stuck_at_half)} ({len(stuck_at_half)/len(df)*100:.1f}%)")
print(f"Their volume_fp stats:\n{stuck_at_half['volume_fp'].describe()}\n")

print(f"Rows NOT at 0.5: {len(not_stuck)}")
print(f"Their volume_fp stats:\n{not_stuck['volume_fp'].describe()}")
