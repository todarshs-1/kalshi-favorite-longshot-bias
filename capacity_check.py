"""
capacity_check.py

Every backtest so far assumed we could always buy exactly as many contracts
as we wanted, at exactly the recorded price, regardless of how big our
bankroll grows. That's unrealistic at scale -- real markets have finite
liquidity, and trying to buy a large fraction of a market's actual traded
volume would move the price against us in ways this backtest can't see.

This script checks: for each trade we WOULD have placed (at the $1,000
starting bankroll), what fraction of that specific market's real historical
volume (volume_fp) would our purchase represent? Since Kelly-sized stakes
scale roughly linearly with bankroll once capped at MAX_STAKE_FRACTION, we
can estimate at what bankroll MULTIPLE this strategy would start consuming
an uncomfortably large share of real market volume -- without needing to
literally re-run the simulation at every possible bankroll size.
"""

import math
import pandas as pd
from sklearn.isotonic import IsotonicRegression

THRESHOLD = 0.15
STARTING_BANKROLL = 1000.00
KELLY_FRACTION = 0.5
MAX_STAKE_FRACTION = 0.05

# Fractions of a market's historical volume we'd consider a meaningful
# liquidity concern -- standard market-impact heuristics start flagging
# concern well before you'd actually be trying to buy the whole market.
CONCERN_LEVELS = [0.01, 0.05, 0.10, 0.25, 0.50, 1.00]


def kalshi_fee(contracts, price):
    raw_fee = 0.07 * contracts * price * (1 - price)
    return math.ceil(raw_fee * 100) / 100


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

trades = test[test["implied_probability"] <= THRESHOLD].copy()
trades["calibrated_yes_prob"] = model.predict(trades["implied_probability"])
trades["close_date"] = trades["close_time"].dt.date
trades["no_price"] = 1 - trades["implied_probability"]
trades["true_p_no"] = 1 - trades["calibrated_yes_prob"]
trades["kelly_f"] = ((trades["true_p_no"] - trades["no_price"])
                      / (1 - trades["no_price"])).clip(lower=0)

bankroll = STARTING_BANKROLL
trade_log = []

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

        if row["actual_outcome"] == 0:
            day_pnl += contracts * 1.00 - cost
        else:
            day_pnl -= cost

        # This is the new part: compare our contract purchase to the
        # market's REAL historical volume for this specific contract.
        volume = row["volume_fp"]
        fraction_of_volume = contracts / volume if volume > 0 else None

        trade_log.append({
            "ticker": row["ticker"],
            "series": row["series"],
            "contracts": contracts,
            "volume_fp": volume,
            "fraction_of_volume": fraction_of_volume,
        })

    bankroll = day_start_bankroll + day_pnl

trade_df = pd.DataFrame(trade_log).dropna(subset=["fraction_of_volume"])

print(f"Trades analyzed: {len(trade_df)} (at ${STARTING_BANKROLL:.0f} starting bankroll)\n")
print("--- At current ($1,000) bankroll, fraction of real market volume consumed per trade ---")
print(trade_df["fraction_of_volume"].describe())

avg_fraction = trade_df["fraction_of_volume"].mean()
max_fraction = trade_df["fraction_of_volume"].max()
median_fraction = trade_df["fraction_of_volume"].median()

print(f"\n--- Estimated bankroll multiple where concern levels are reached ---")
print(f"(assumes roughly linear scaling of stake size with bankroll)\n")
print(f"{'Concern level':>15} {'Multiple (avg trade)':>22} {'Implied bankroll':>18} {'Multiple (worst trade)':>24}")
for level in CONCERN_LEVELS:
    avg_multiple = level / avg_fraction if avg_fraction > 0 else float("inf")
    worst_multiple = level / max_fraction if max_fraction > 0 else float("inf")
    implied_bankroll = STARTING_BANKROLL * avg_multiple
    print(f"{level*100:>14.0f}% {avg_multiple:>22.1f}x {'$' + format(implied_bankroll, ',.0f'):>18} {worst_multiple:>23.1f}x")

print("\n--- How to read this ---")
print("'Multiple (avg trade)' = how many times bigger your bankroll would need")
print("to be before your AVERAGE trade starts consuming that %% of real volume.")
print("'Multiple (worst trade)' = same, but for your single most volume-hungry")
print("trade -- the market where you'd hit a liquidity wall FIRST.")

print("\n--- Worst 10 trades by fraction of volume consumed (at $1,000 bankroll) ---")
worst = trade_df.nlargest(10, "fraction_of_volume")[["ticker", "series", "contracts", "volume_fp", "fraction_of_volume"]]
pd.set_option("display.float_format", "{:.4f}".format)
print(worst.to_string(index=False))
