"""
kelly_backtest.py (fixed)

Same Kelly-sized strategy as before, but fixes a real bug: the previous
version sized each trade off the bankroll AFTER the previous trade settled,
as if trades happen one at a time in sequence. In reality, many trades
close on the SAME DAY (multiple games, multiple cities) -- your capital is
split across all of them simultaneously, and you don't find out who won
until they all settle together.

Fix: group trades by close date. All trades on the same day are sized off
the SAME starting bankroll (the bankroll at the start of that day), with a
running cap so we never deploy more than 100% of that day's bankroll across
all of that day's trades combined. Bankroll only updates once, at the end
of each day, after all of that day's trades have settled.
"""

import math
import pandas as pd
from sklearn.isotonic import IsotonicRegression

THRESHOLD = 0.15
STARTING_BANKROLL = 1000.00
KELLY_FRACTION = 0.5
MAX_STAKE_FRACTION = 0.05  # per trade, as a fraction of that DAY's starting bankroll
MAX_VOLUME_FRACTION = 0.10  # never buy more than 10% of a market's REAL historical volume


def kalshi_fee(contracts, price):
    raw_fee = 0.07 * contracts * price * (1 - price)
    return math.ceil(raw_fee * 100) / 100


df = pd.read_csv("kalshi_combined_settled.csv", encoding="latin-1")
df = df[df["result"].isin(["yes", "no"])].copy()
df = df[~df["series"].isin(["KXNBAPTS", "KXNBAREB"])].copy()
df["actual_outcome"] = (df["result"] == "yes").astype(int)
df["close_time"] = pd.to_datetime(df["close_time"], format="ISO8601")

# Same fix as walk_forward_backtest.py -- exclude degenerate 0%/100%
# implied probabilities, which cause division by zero in the Kelly formula.
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
trades["close_date"] = trades["close_time"].dt.date  # group by CALENDAR DAY

print(f"Test period: from {split_date.date()} onward")
print(f"Trades matching strategy (implied_probability <= {THRESHOLD}): {len(trades)}")
print(f"Spread across {trades['close_date'].nunique()} distinct calendar days\n")

bankroll = STARTING_BANKROLL
peak_bankroll = STARTING_BANKROLL
max_drawdown_pct = 0.0
daily_log = []
trade_log = []
n_liquidity_capped = 0
n_liquidity_blocked = 0

for close_date, day_trades in trades.groupby("close_date"):
    day_start_bankroll = bankroll  # everyone this day sizes off THIS number
    deployed_today = 0.0
    day_pnl = 0.0
    trades_placed_today = 0

    # Sort by edge (largest first) so if capital runs out mid-day, the
    # best opportunities get funded first -- a reasonable, explicit rule.
    day_trades = day_trades.copy()
    day_trades["no_price"] = 1 - day_trades["implied_probability"]
    day_trades["true_p_no"] = 1 - day_trades["calibrated_yes_prob"]
    day_trades["kelly_f"] = ((day_trades["true_p_no"] - day_trades["no_price"])
                              / (1 - day_trades["no_price"])).clip(lower=0)
    day_trades = day_trades.sort_values("kelly_f", ascending=False)

    for _, row in day_trades.iterrows():
        no_price = row["no_price"]
        stake_fraction = min(row["kelly_f"] * KELLY_FRACTION, MAX_STAKE_FRACTION)
        if stake_fraction <= 0:
            continue

        desired_stake = day_start_bankroll * stake_fraction
        remaining_capital = day_start_bankroll - deployed_today
        actual_stake = min(desired_stake, remaining_capital)

        if actual_stake < no_price:
            continue  # not enough remaining capital today to buy even 1 contract

        contracts = math.floor(actual_stake / no_price)
        if contracts < 1:
            continue

        # LIQUIDITY CAP: never buy more than MAX_VOLUME_FRACTION of what
        # this specific market has ever actually traded, historically.
        # Without this, Kelly sizing can size a trade based only on
        # bankroll/edge with no idea the market itself is too thin to
        # fill an order that large -- which is exactly what capacity_check.py
        # found was happening (one trade tried to buy 793% of a market's
        # entire lifetime volume).
        volume = row["volume_fp"]
        max_contracts_by_liquidity = math.floor(MAX_VOLUME_FRACTION * volume) if volume > 0 else 0
        if max_contracts_by_liquidity < contracts:
            n_liquidity_capped += 1
        contracts = min(contracts, max_contracts_by_liquidity)
        if contracts < 1:
            n_liquidity_blocked += 1
            continue  # market too thin to trade at all, even at the cap

        fee = kalshi_fee(contracts, no_price)
        cost = contracts * no_price + fee
        deployed_today += cost
        trades_placed_today += 1

        if row["actual_outcome"] == 0:  # NO won
            profit = contracts * 1.00 - cost
        else:
            profit = -cost

        day_pnl += profit
        trade_log.append({"close_date": close_date, "contracts": contracts,
                           "won": row["actual_outcome"] == 0, "profit": profit})

    bankroll = day_start_bankroll + day_pnl  # ONE update, at end of day
    peak_bankroll = max(peak_bankroll, bankroll)
    drawdown_pct = (bankroll - peak_bankroll) / peak_bankroll * 100
    max_drawdown_pct = min(max_drawdown_pct, drawdown_pct)

    daily_log.append({"close_date": close_date, "trades_placed": trades_placed_today,
                       "day_pnl": day_pnl, "bankroll_after": bankroll})

daily_df = pd.DataFrame(daily_log)
trade_df = pd.DataFrame(trade_log)

print("--- Results ---")
print(f"Total trades actually placed: {len(trade_df)}")
print(f"Trades REDUCED by liquidity cap: {n_liquidity_capped}")
print(f"Trades BLOCKED entirely (market too thin): {n_liquidity_blocked}")
print(f"Starting bankroll:  ${STARTING_BANKROLL:.2f}")
print(f"Ending bankroll:    ${bankroll:.2f}")
print(f"Total return:       {(bankroll - STARTING_BANKROLL) / STARTING_BANKROLL * 100:.2f}%")
print(f"Max drawdown:       {max_drawdown_pct:.2f}%")
if len(trade_df) > 0:
    print(f"Win rate:           {trade_df['won'].mean():.2%}")

print("\n--- First 10 days ---")
print(daily_df.head(10).to_string(index=False))
print("\n--- Last 10 days ---")
print(daily_df.tail(10).to_string(index=False))
