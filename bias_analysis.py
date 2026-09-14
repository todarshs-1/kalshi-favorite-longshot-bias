"""
bias_analysis.py

The core test: does the market's implied probability match the actual rate
that 'yes' happened? We bucket markets by implied probability and compare
each bucket's average implied probability to its actual observed win rate.

Favorite-longshot bias = low-probability buckets have an ACTUAL rate lower
than their IMPLIED probability (longshots overpriced), and/or high-probability
buckets have an actual rate higher than implied (favorites underpriced).
"""

import pandas as pd

df = pd.read_csv("kalshi_combined_settled.csv", encoding="latin-1")

# Drop non-binary markets -- 'scalar' markets aren't yes/no bets, they don't fit this test.
df = df[df["result"].isin(["yes", "no"])].copy()

# Drop NBA prop ladder markets (KXNBAPTS, KXNBAREB). We confirmed via
# inspect_prop_market.py that these have internally inconsistent prices --
# e.g. a 15+ points threshold priced LOWER than a 20+ points threshold on
# the same player/game, which is logically impossible for real-time odds.
# This happens because each threshold in the ladder stops trading at a
# different moment once its outcome becomes obvious, so last_price_dollars
# captures snapshots frozen at different times, not one coherent forecast.
# Game-winner markets and weather markets trade continuously and don't have
# this problem, so we keep those.
excluded_series = ["KXNBAPTS", "KXNBAREB"]
n_before = len(df)
df = df[~df["series"].isin(excluded_series)].copy()
n_excluded = n_before - len(df)
print(f"Excluded {n_excluded} rows from prop ladder markets ({', '.join(excluded_series)})")
print(f"Remaining: {len(df)} rows from liquid, continuously-traded markets\n")

# Convert result into a 1/0 number so we can average it.
df["actual_outcome"] = (df["result"] == "yes").astype(int)

# Bucket implied_probability into 10 bins: 0-10%, 10-20%, ..., 90-100%.
bins = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
df["bucket"] = pd.cut(df["implied_probability"], bins=bins, include_lowest=True)

# For each bucket: how many markets, what was the average implied probability,
# and what fraction actually resolved to 'yes'?
summary = df.groupby("bucket", observed=True).agg(
    n_markets=("actual_outcome", "count"),
    avg_implied_prob=("implied_probability", "mean"),
    actual_win_rate=("actual_outcome", "mean"),
)

summary["difference"] = summary["actual_win_rate"] - summary["avg_implied_prob"]

pd.set_option("display.float_format", "{:.4f}".format)
print(summary)

print("\n--- How to read this ---")
print("If 'difference' is negative in low-probability buckets, longshots")
print("are winning LESS than the market implied -- classic overpricing.")
print("If 'difference' is positive in high-probability buckets, favorites")
print("are winning MORE than implied -- favorites are underpriced.")

# Split by series to check whether one type of market (e.g. weather) is
# behaving very differently from the others -- large, uniform miscalibration
# across ALL buckets (not just extremes) usually signals a data problem,
# not a real behavioral bias.
print("\n\n=== Same test, broken out by series ===")
for series_name, group in df.groupby("series"):
    group_summary = group.groupby("bucket", observed=True).agg(
        n_markets=("actual_outcome", "count"),
        avg_implied_prob=("implied_probability", "mean"),
        actual_win_rate=("actual_outcome", "mean"),
    )
    group_summary["difference"] = group_summary["actual_win_rate"] - group_summary["avg_implied_prob"]
    print(f"\n--- {series_name} (n={len(group)}) ---")
    print(group_summary)
