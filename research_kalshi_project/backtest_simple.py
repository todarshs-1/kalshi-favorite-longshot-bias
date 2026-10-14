"""
backtest_simple.py

The simplest version of a trading strategy based on our finding: extreme
longshots (<=10% implied probability) are significantly overpriced on
Kalshi. Strategy: whenever a market is priced at or below the threshold,
bet AGAINST it (buy the "NO" side). Since longshots rarely hit, "NO" should
win most of the time -- but we need to check if the edge survives real fees.

Tested ONLY on the test set (post-April 18, 2026) -- the same out-of-sample
data from calibration_model.py -- so this isn't just re-describing a
pattern we already know is in the training data.
"""

import math
import pandas as pd

THRESHOLD = 0.10       # bet against any market priced at or below this
CONTRACTS_PER_TRADE = 1  # flat position size -- 1 contract per bet


def kalshi_fee(contracts, price):
    """Kalshi's published taker fee formula: 0.07 * C * P * (1-P),
    rounded UP to the next cent.
    """
    raw_fee = 0.07 * contracts * price * (1 - price)
    return math.ceil(raw_fee * 100) / 100  # round up to nearest cent


df = pd.read_csv("kalshi_combined_settled.csv", encoding="latin-1")
df = df[df["result"].isin(["yes", "no"])].copy()
df = df[~df["series"].isin(["KXNBAPTS", "KXNBAREB"])].copy()
df["actual_outcome"] = (df["result"] == "yes").astype(int)
df["close_time"] = pd.to_datetime(df["close_time"], format="ISO8601")
df = df.sort_values("close_time").reset_index(drop=True)

# Same time-based 80/20 split as calibration_model.py, so this is the
# same honest out-of-sample data.
split_index = int(len(df) * 0.8)
split_date = df.loc[split_index, "close_time"]
test = df[df["close_time"] >= split_date].copy()

# The actual strategy: only trade markets at or below the threshold.
trades = test[test["implied_probability"] <= THRESHOLD].copy()

print(f"Test period starts: {split_date.date()}")
print(f"Markets available in test period: {len(test)}")
print(f"Markets matching strategy (implied_probability <= {THRESHOLD}): {len(trades)}\n")

# Simulate each trade: we buy the NO side of a longshot market.
# NO price is approximated as (1 - implied_probability) -- we don't have a
# directly-pulled NO price field, so this assumes yes_price + no_price ~= 1,
# a standard approximation, not an exact trade price. Worth stating as a
# limitation in the paper.
results = []
for _, row in trades.iterrows():
    no_price = 1 - row["implied_probability"]
    fee = kalshi_fee(CONTRACTS_PER_TRADE, no_price)
    cost = no_price * CONTRACTS_PER_TRADE + fee

    if row["actual_outcome"] == 0:  # result was "no" -- our bet won
        payout = 1.00 * CONTRACTS_PER_TRADE
        profit = payout - cost
    else:  # result was "yes" -- our bet lost
        profit = -cost

    results.append({
        "close_time": row["close_time"],
        "ticker": row["ticker"],
        "series": row["series"],
        "implied_probability": row["implied_probability"],
        "no_price": no_price,
        "fee": fee,
        "won": row["actual_outcome"] == 0,
        "profit": profit,
    })

results_df = pd.DataFrame(results).sort_values("close_time").reset_index(drop=True)
results_df["cumulative_profit"] = results_df["profit"].cumsum()

total_trades = len(results_df)
win_rate = results_df["won"].mean()
total_profit = results_df["profit"].sum()
total_staked = (1 - results_df["implied_probability"]).sum() + results_df["fee"].sum()
roi_pct = (total_profit / total_staked) * 100 if total_staked > 0 else 0
total_fees = results_df["fee"].sum()

# Max drawdown: the largest drop from a running peak in cumulative profit.
running_max = results_df["cumulative_profit"].cummax()
drawdown = results_df["cumulative_profit"] - running_max
max_drawdown = drawdown.min()

print("--- Results ---")
print(f"Total trades:        {total_trades}")
print(f"Win rate:            {win_rate:.2%}")
print(f"Total fees paid:     ${total_fees:.2f}")
print(f"Total profit:        ${total_profit:.2f}")
print(f"Total staked:        ${total_staked:.2f}")
print(f"ROI:                 {roi_pct:.2f}%")
print(f"Max drawdown:        ${max_drawdown:.2f}")

# Monthly breakdown so we can see if the edge is steady or lumpy.
results_df["month"] = results_df["close_time"].dt.to_period("M")
monthly = results_df.groupby("month").agg(
    n_trades=("profit", "count"),
    monthly_profit=("profit", "sum"),
    win_rate=("won", "mean"),
)
print("\n--- Monthly breakdown ---")
print(monthly)
