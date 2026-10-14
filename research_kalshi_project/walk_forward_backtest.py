"""
walk_forward_backtest.py

Instead of one train/test split, this splits the full dataset into several
SEQUENTIAL windows. For each window, we train the calibration model on
everything BEFORE that window, then test the strategy only on that window.
This gives us multiple independent looks at performance across different
time periods (different NBA/MLB seasons, different weather seasons) --
if the edge is real and durable, it should show up consistently across
most windows, not just one lucky stretch.
"""

import math
import pandas as pd
from sklearn.isotonic import IsotonicRegression

THRESHOLD = 0.15
STARTING_BANKROLL = 1000.00
KELLY_FRACTION = 0.5
MAX_STAKE_FRACTION = 0.05
N_WINDOWS = 5  # split the test period into this many sequential chunks


def kalshi_fee(contracts, price):
    raw_fee = 0.07 * contracts * price * (1 - price)
    return math.ceil(raw_fee * 100) / 100


def run_window(train_df, test_df):
    """Fit the model on train_df, run the Kelly strategy on test_df.
    Returns a dict of summary results for this one window.
    """
    if len(train_df) < 100 or len(test_df) == 0:
        return None

    model = IsotonicRegression(out_of_bounds="clip")
    model.fit(train_df["implied_probability"], train_df["actual_outcome"])

    trades = test_df[test_df["implied_probability"] <= THRESHOLD].copy()
    if len(trades) == 0:
        return None

    trades["calibrated_yes_prob"] = model.predict(trades["implied_probability"])
    trades["close_date"] = trades["close_time"].dt.date
    trades["no_price"] = 1 - trades["implied_probability"]
    trades["true_p_no"] = 1 - trades["calibrated_yes_prob"]
    trades["kelly_f"] = ((trades["true_p_no"] - trades["no_price"])
                          / (1 - trades["no_price"])).clip(lower=0)

    bankroll = STARTING_BANKROLL
    peak = STARTING_BANKROLL
    max_dd = 0.0
    n_placed = 0
    n_won = 0

    for close_date, day_trades in trades.groupby("close_date"):
        day_start_bankroll = bankroll
        deployed = 0.0
        day_pnl = 0.0
        day_trades = day_trades.sort_values("kelly_f", ascending=False)

        for _, row in day_trades.iterrows():
            stake_fraction = min(row["kelly_f"] * KELLY_FRACTION, MAX_STAKE_FRACTION)
            if stake_fraction <= 0:
                continue
            desired_stake = day_start_bankroll * stake_fraction
            remaining = day_start_bankroll - deployed
            actual_stake = min(desired_stake, remaining)
            if actual_stake < row["no_price"]:
                continue
            contracts = math.floor(actual_stake / row["no_price"])
            if contracts < 1:
                continue
            fee = kalshi_fee(contracts, row["no_price"])
            cost = contracts * row["no_price"] + fee
            deployed += cost
            n_placed += 1

            if row["actual_outcome"] == 0:
                day_pnl += contracts * 1.00 - cost
                n_won += 1
            else:
                day_pnl -= cost

        bankroll = day_start_bankroll + day_pnl
        peak = max(peak, bankroll)
        max_dd = min(max_dd, (bankroll - peak) / peak * 100)

    return {
        "n_train": len(train_df),
        "n_test_candidates": len(trades),
        "n_placed": n_placed,
        "win_rate": n_won / n_placed if n_placed > 0 else None,
        "start_bankroll": STARTING_BANKROLL,
        "end_bankroll": bankroll,
        "return_pct": (bankroll - STARTING_BANKROLL) / STARTING_BANKROLL * 100,
        "max_drawdown_pct": max_dd,
    }


df = pd.read_csv("kalshi_combined_settled.csv", encoding="latin-1")
df = df[df["result"].isin(["yes", "no"])].copy()
df = df[~df["series"].isin(["KXNBAPTS", "KXNBAREB"])].copy()
df["actual_outcome"] = (df["result"] == "yes").astype(int)
df["close_time"] = pd.to_datetime(df["close_time"], format="ISO8601")

# Kalshi prices only trade in 1-cent increments from $0.01 to $0.99 -- a
# literal implied_probability of exactly 0.0 or 1.0 isn't a real tradeable
# price, it's a default/edge-case value (same category as the bid/ask
# reset bug we found earlier). These cause a division-by-zero in the
# Kelly formula, so we exclude them here.
n_before = len(df)
df = df[(df["implied_probability"] > 0) & (df["implied_probability"] < 1)].copy()
print(f"Excluded {n_before - len(df)} rows with degenerate 0%% or 100%% implied probability")

df = df.sort_values("close_time").reset_index(drop=True)

# Use only the back half of the dataset for walk-forward windows (need
# real training history behind each window), split that back half into
# N_WINDOWS equal sequential chunks.
halfway = len(df) // 2
walk_forward_region = df.iloc[halfway:].reset_index(drop=True)
window_size = len(walk_forward_region) // N_WINDOWS

print(f"Total dataset: {len(df)} rows")
print(f"Walk-forward region: {len(walk_forward_region)} rows, split into {N_WINDOWS} windows\n")

results = []
for i in range(N_WINDOWS):
    window_start_idx = i * window_size
    window_end_idx = (i + 1) * window_size if i < N_WINDOWS - 1 else len(walk_forward_region)
    test_window = walk_forward_region.iloc[window_start_idx:window_end_idx]

    if len(test_window) == 0:
        continue

    # Train on EVERYTHING before this window's start date (expanding window)
    window_start_date = test_window["close_time"].min()
    train_data = df[df["close_time"] < window_start_date]

    result = run_window(train_data, test_window)
    if result:
        result["window"] = i + 1
        result["date_range"] = f"{test_window['close_time'].min().date()} to {test_window['close_time'].max().date()}"
        results.append(result)

results_df = pd.DataFrame(results)
cols = ["window", "date_range", "n_train", "n_placed", "win_rate", "return_pct", "max_drawdown_pct"]
pd.set_option("display.width", 140)
pd.set_option("display.float_format", "{:.2f}".format)
print(results_df[cols].to_string(index=False))

print("\n--- How to read this ---")
print("If return_pct is consistently positive across ALL windows, the edge")
print("looks durable. If it's wildly inconsistent (some huge, some negative),")
print("the earlier single-window result was likely luck, not a real edge.")
