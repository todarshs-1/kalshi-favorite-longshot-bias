"""
check_prop_liquidity.py

Tests whether the massive miscalibration in KXNBAPTS/KXNBAREB middle
buckets is explained by thin trading volume -- i.e. whether last_price_dollars
is a stale, unreliable price on markets nobody actively traded near game time.
"""

import pandas as pd

df = pd.read_csv("kalshi_combined_settled.csv", encoding="latin-1")
df = df[df["result"].isin(["yes", "no"])].copy()
df["actual_outcome"] = (df["result"] == "yes").astype(int)

bins = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
df["bucket"] = pd.cut(df["implied_probability"], bins=bins, include_lowest=True)

props_only = df[df["series"].isin(["KXNBAPTS", "KXNBAREB"])]

summary = props_only.groupby("bucket", observed=True).agg(
    n_markets=("actual_outcome", "count"),
    avg_implied_prob=("implied_probability", "mean"),
    actual_win_rate=("actual_outcome", "mean"),
    median_volume=("volume_fp", "median"),
    volume_25th_pct=("volume_fp", lambda x: x.quantile(0.25)),
)
summary["difference"] = summary["actual_win_rate"] - summary["avg_implied_prob"]

pd.set_option("display.float_format", "{:.4f}".format)
print(summary)
