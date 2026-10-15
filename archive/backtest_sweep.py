"""
backtest_sweep.py

Combined sweep: tests every combination of threshold x starting bankroll,
with the real liquidity cap applied, to find where return is actually
maximized once both the statistical edge AND real market capacity are
accounted for together.
"""

import math
import pandas as pd
from sklearn.isotonic import IsotonicRegression

THRESHOLDS_TO_TEST = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
BANKROLLS_TO_TEST = [1000, 10000, 50000]
KELLY_FRACTION = 0.5
MAX_STAKE_FRACTION = 0.05
MAX_VOLUME_FRACTION = 0.10


def kalshi_fee(contracts, price):
    raw_fee = 0.07 * contracts * price * (1 - price)
    return math.ceil(raw_fee * 100) / 100


def run_backtest(trades, starting_bankroll):
    bankroll = starting_bankroll
    peak_bankroll = starting_bankroll
    max_drawdown_pct = 0.0
    n_placed = 0
    n_capped = 0

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

            volume = row["volume_fp"]
            max_by_liquidity = math.floor(MAX_VOLUME_FRACTION * volume) if volume > 0 else 0
            if max_by_liquidity < contracts:
                n_capped += 1
            contracts = min(contracts, max_by_liquidity)
            if contracts < 1:
                continue

            fee = kalshi_fee(contracts, row["no_price"])
            cost = contracts * row["no_price"] + fee
            deployed += cost
            n_placed += 1

            if row["actual_outcome"] == 0:
                day_pnl += contracts * 1.00 - cost
            else:
                day_pnl -= cost

        bankroll = day_start_bankroll + day_pnl
        peak_bankroll = max(peak_bankroll, bankroll)
        drawdown_pct = (bankroll - peak_bankroll) / peak_bankroll * 100
        max_drawdown_pct = min(max_drawdown_pct, drawdown_pct)

    return {
        "return_pct": (bankroll - starting_bankroll) / starting_bankroll * 100,
        "n_trades_placed": n_placed,
        "n_trades_capped": n_capped,
        "max_drawdown_pct": max_drawdown_pct,
    }


df = pd.read_csv("kalshi_combined_settled.csv", encoding="latin-1")
df = df[df["result"].isin(["yes", "no"])].copy()
df = df[~df["series"].isin(["KXNBAPTS", "KXNBAREB"])].copy()
df["actual_outcome"] = (df["result"] == "yes").astype(int)
df["close_time"] = pd.to_datetime(df["close_time"], format="ISO8601")
df = df[(df["implied_probability"] > 0) & (df["implied_probability"] < 1)].copy()
df = df.sort_values("close_time").reset_index(drop=True)

split_index = int(len(df) * 0.8)
split_date = df.loc[split_index, "close_time"]
train = df[df["close_time"] < split_date].copy()
test = df[df["close_time"] >= split_date].copy()

model = IsotonicRegression(out_of_bounds="clip")
model.fit(train["implied_probability"], train["actual_outcome"])

print(f"Test period: from {split_date.date()} onward\n")

rows = []
for threshold in THRESHOLDS_TO_TEST:
    trades = test[test["implied_probability"] <= threshold].copy()
    if len(trades) == 0:
        continue
    trades["calibrated_yes_prob"] = model.predict(trades["implied_probability"])
    trades["close_date"] = trades["close_time"].dt.date
    trades["no_price"] = 1 - trades["implied_probability"]
    trades["true_p_no"] = 1 - trades["calibrated_yes_prob"]
    trades["kelly_f"] = ((trades["true_p_no"] - trades["no_price"])
                          / (1 - trades["no_price"])).clip(lower=0)

    for bankroll in BANKROLLS_TO_TEST:
        result = run_backtest(trades, bankroll)
        result["threshold"] = threshold
        result["bankroll"] = bankroll
        rows.append(result)

results_df = pd.DataFrame(rows)
cols = ["threshold", "bankroll", "return_pct", "n_trades_placed", "n_trades_capped", "max_drawdown_pct"]
pd.set_option("display.width", 150)
pd.set_option("display.float_format", "{:.2f}".format)
print(results_df[cols].to_string(index=False))

print("\n--- Best threshold per bankroll size ---")
for bankroll in BANKROLLS_TO_TEST:
    subset = results_df[results_df["bankroll"] == bankroll]
    best = subset.loc[subset["return_pct"].idxmax()]
    print(f"${bankroll:,}: best threshold = {best['threshold']}, return = {best['return_pct']:.2f}%")
