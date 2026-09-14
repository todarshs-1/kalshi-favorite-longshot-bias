"""
walk_forward_favorites.py

Tests the MIRROR strategy: instead of fading overpriced longshots (buying
NO on cheap contracts), this backs underpriced favorites (buying YES on
expensive contracts, >=90% implied probability -- the region our
significance test showed was a real, if smaller, effect: favorites winning
slightly MORE often than the market price implied).

Same walk-forward validation approach as walk_forward_backtest.py, so this
is held to the same standard of evidence.
"""

import math
import pandas as pd
from sklearn.isotonic import IsotonicRegression

THRESHOLD = 0.90   # only trade favorites priced at or above this
STARTING_BANKROLL = 1000.00
KELLY_FRACTION = 0.5
MAX_STAKE_FRACTION = 0.05
N_WINDOWS = 5


def kalshi_fee(contracts, price):
    raw_fee = 0.07 * contracts * price * (1 - price)
    return math.ceil(raw_fee * 100) / 100


def run_window(train_df, test_df):
    if len(train_df) < 100 or len(test_df) == 0:
        return None

    model = IsotonicRegression(out_of_bounds="clip")
    model.fit(train_df["implied_probability"], train_df["actual_outcome"])

    # The key difference from the longshot version: we select HIGH
    # probability markets and buy YES, not low probability markets buying NO.
    trades = test_df[test_df["implied_probability"] >= THRESHOLD].copy()
    if len(trades) == 0:
        return None

    trades["calibrated_yes_prob"] = model.predict(trades["implied_probability"])
    trades["close_date"] = trades["close_time"].dt.date
    trades["yes_price"] = trades["implied_probability"]       # price paid for YES
    trades["true_p_yes"] = trades["calibrated_yes_prob"]       # our model's estimate
    trades["kelly_f"] = ((trades["true_p_yes"] - trades["yes_price"])
                          / (1 - trades["yes_price"])).clip(lower=0)

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
            if actual_stake < row["yes_price"]:
                continue
            contracts = math.floor(actual_stake / row["yes_price"])
            if contracts < 1:
                continue
            fee = kalshi_fee(contracts, row["yes_price"])
            cost = contracts * row["yes_price"] + fee
            deployed += cost
            n_placed += 1

            if row["actual_outcome"] == 1:  # YES won
                day_pnl += contracts * 1.00 - cost
                n_won += 1
            else:
                day_pnl -= cost

        bankroll = day_start_bankroll + day_pnl
        peak = max(peak, bankroll)
        max_dd = min(max_dd, (bankroll - peak) / peak * 100)

    return {
        "n_train": len(train_df),
        "n_placed": n_placed,
        "win_rate": n_won / n_placed if n_placed > 0 else None,
        "end_bankroll": bankroll,
        "return_pct": (bankroll - STARTING_BANKROLL) / STARTING_BANKROLL * 100,
        "max_drawdown_pct": max_dd,
    }


df = pd.read_csv("kalshi_combined_settled.csv", encoding="latin-1")
df = df[df["result"].isin(["yes", "no"])].copy()
df = df[~df["series"].isin(["KXNBAPTS", "KXNBAREB"])].copy()
df["actual_outcome"] = (df["result"] == "yes").astype(int)
df["close_time"] = pd.to_datetime(df["close_time"], format="ISO8601")
df = df[(df["implied_probability"] > 0) & (df["implied_probability"] < 1)].copy()
df = df.sort_values("close_time").reset_index(drop=True)

halfway = len(df) // 2
walk_forward_region = df.iloc[halfway:].reset_index(drop=True)
window_size = len(walk_forward_region) // N_WINDOWS

print(f"Total dataset: {len(df)} rows")
print(f"Walk-forward region: {len(walk_forward_region)} rows, split into {N_WINDOWS} windows\n")

results = []
for i in range(N_WINDOWS):
    start_idx = i * window_size
    end_idx = (i + 1) * window_size if i < N_WINDOWS - 1 else len(walk_forward_region)
    test_window = walk_forward_region.iloc[start_idx:end_idx]
    if len(test_window) == 0:
        continue

    window_start_date = test_window["close_time"].min()
    train_data = df[df["close_time"] < window_start_date]

    result = run_window(train_data, test_window)
    if result:
        result["window"] = i + 1
        result["date_range"] = f"{test_window['close_time'].min().date()} to {test_window['close_time'].max().date()}"
        results.append(result)

results_df = pd.DataFrame(results)
cols = ["window", "date_range", "n_placed", "win_rate", "return_pct", "max_drawdown_pct"]
pd.set_option("display.width", 140)
pd.set_option("display.float_format", "{:.2f}".format)
print(results_df[cols].to_string(index=False))
