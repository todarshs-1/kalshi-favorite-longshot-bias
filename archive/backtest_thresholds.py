"""
backtest_thresholds.py

Runs the same simple fade-the-longshot strategy at several different
probability thresholds, to see where the edge actually survives fees
best -- rather than assuming the original 10% cutoff was optimal.
"""

import math
import pandas as pd

CONTRACTS_PER_TRADE = 1
THRESHOLDS_TO_TEST = [0.01, 0.02, 0.03, 0.05, 0.07, 0.10, 0.15, 0.20, 0.25, 0.30]


def kalshi_fee(contracts, price):
    raw_fee = 0.07 * contracts * price * (1 - price)
    return math.ceil(raw_fee * 100) / 100


def run_backtest(test_df, threshold):
    trades = test_df[test_df["implied_probability"] <= threshold].copy()
    if len(trades) == 0:
        return None

    profits = []
    fees = []
    wins = []

    for _, row in trades.iterrows():
        no_price = 1 - row["implied_probability"]
        fee = kalshi_fee(CONTRACTS_PER_TRADE, no_price)
        cost = no_price * CONTRACTS_PER_TRADE + fee

        if row["actual_outcome"] == 0:
            profit = 1.00 * CONTRACTS_PER_TRADE - cost
            wins.append(True)
        else:
            profit = -cost
            wins.append(False)

        profits.append(profit)
        fees.append(fee)

    profits_series = pd.Series(profits)
    total_staked = (1 - trades["implied_probability"]).sum() + sum(fees)

    return {
        "threshold": threshold,
        "n_trades": len(trades),
        "win_rate": sum(wins) / len(wins),
        "total_fees": sum(fees),
        "total_profit": profits_series.sum(),
        "total_staked": total_staked,
        "roi_pct": (profits_series.sum() / total_staked * 100) if total_staked > 0 else 0,
        "profit_per_trade": profits_series.mean(),
    }


df = pd.read_csv("kalshi_combined_settled.csv", encoding="latin-1")
df = df[df["result"].isin(["yes", "no"])].copy()
df = df[~df["series"].isin(["KXNBAPTS", "KXNBAREB"])].copy()
df["actual_outcome"] = (df["result"] == "yes").astype(int)
df["close_time"] = pd.to_datetime(df["close_time"], format="ISO8601")
df = df.sort_values("close_time").reset_index(drop=True)

split_index = int(len(df) * 0.8)
split_date = df.loc[split_index, "close_time"]
test = df[df["close_time"] >= split_date].copy()

print(f"Test period: from {split_date.date()} onward ({len(test)} total markets)\n")

rows = []
for threshold in THRESHOLDS_TO_TEST:
    result = run_backtest(test, threshold)
    if result:
        rows.append(result)

summary = pd.DataFrame(rows)
pd.set_option("display.float_format", "{:.4f}".format)
pd.set_option("display.width", 120)
print(summary.to_string(index=False))

print("\n--- How to read this ---")
print("roi_pct = return on capital staked, after fees")
print("profit_per_trade = average dollars won/lost per trade")
print("Look for the threshold with the best roi_pct AND a large enough")
print("n_trades to trust the result isn't just luck.")
