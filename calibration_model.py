"""
calibration_model.py

Builds an isotonic regression calibration curve: a model that maps
"the market's stated implied probability" -> "our best estimate of the
REAL probability," based on what we observed actually happened.

Isotonic regression specifically enforces that the curve can only go up
(or stay flat) as implied probability increases -- it can never predict
that a 20% contract is more likely to hit than a 25% contract. That
constraint matches how real probabilities must behave, and is why this
technique (not a generic curve-fit) is the standard tool for this kind
of calibration problem.

We fit the curve on OLDER markets (train) and test it on NEWER markets
it has never seen (test) -- a time-based split, not a random shuffle,
since paired markets from the same event share almost the same close_time
and we don't want to leak one side of a pair into training and the other
into testing.
"""

import pandas as pd
from sklearn.isotonic import IsotonicRegression

df = pd.read_csv("kalshi_combined_settled.csv", encoding="latin-1")

df = df[df["result"].isin(["yes", "no"])].copy()
excluded_series = ["KXNBAPTS", "KXNBAREB"]
df = df[~df["series"].isin(excluded_series)].copy()
df["actual_outcome"] = (df["result"] == "yes").astype(int)

# Parse close_time into a real datetime so we can sort and split by it.
df["close_time"] = pd.to_datetime(df["close_time"], format="ISO8601")
df = df.sort_values("close_time").reset_index(drop=True)

# Time-based 80/20 split: train on the OLDER 80% of markets, test on the
# NEWER 20%. This simulates "would this model have actually helped you
# going forward," which a random shuffle would not honestly test.
split_index = int(len(df) * 0.8)
split_date = df.loc[split_index, "close_time"]

train = df[df["close_time"] < split_date].copy()
test = df[df["close_time"] >= split_date].copy()

print(f"Total markets: {len(df)}")
print(f"Train set: {len(train)} markets (before {split_date.date()})")
print(f"Test set:  {len(test)} markets (from {split_date.date()} onward)\n")

# Fit isotonic regression: X = market's implied probability, y = what
# actually happened (1 or 0). out_of_bounds='clip' means if the test set
# ever has a probability outside the range we trained on, we just use the
# nearest edge of the curve instead of erroring out.
model = IsotonicRegression(out_of_bounds="clip")
model.fit(train["implied_probability"], train["actual_outcome"])

# Apply the fitted curve to the UNSEEN test set.
test["calibrated_probability"] = model.predict(test["implied_probability"])

# Compare: does the calibrated model track real outcomes better than the
# raw market price, on data it never trained on?
bins = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
test["bucket"] = pd.cut(test["implied_probability"], bins=bins, include_lowest=True)

comparison = test.groupby("bucket", observed=True).agg(
    n_markets=("actual_outcome", "count"),
    avg_market_price=("implied_probability", "mean"),
    avg_calibrated_prediction=("calibrated_probability", "mean"),
    actual_outcome_rate=("actual_outcome", "mean"),
)
comparison["market_error"] = (comparison["avg_market_price"] - comparison["actual_outcome_rate"]).abs()
comparison["calibrated_error"] = (comparison["avg_calibrated_prediction"] - comparison["actual_outcome_rate"]).abs()

pd.set_option("display.float_format", "{:.4f}".format)
print(comparison)

print("\n--- How to read this ---")
print("market_error = how far the RAW market price was from reality (test set)")
print("calibrated_error = how far our MODEL's prediction was from reality")
print("If calibrated_error is consistently smaller, the model adds real value")
print("beyond just trusting the market's own stated price.")

print(f"\nAverage market_error:     {comparison['market_error'].mean():.4f}")
print(f"Average calibrated_error: {comparison['calibrated_error'].mean():.4f}")
print("(Note: this bucket average is misleading -- it weighs a bucket with")
print("1 market the same as a bucket with 3,000+. See the proper metric below.)")

# Brier score: mean squared error between predicted probability and the
# actual 0/1 outcome, computed across EVERY individual market in the test
# set (not averaged across unequal buckets). This is the standard metric
# for scoring probabilistic predictions, and it naturally weights by how
# much real data we actually have.
test["market_squared_error"] = (test["implied_probability"] - test["actual_outcome"]) ** 2
test["calibrated_squared_error"] = (test["calibrated_probability"] - test["actual_outcome"]) ** 2

market_brier = test["market_squared_error"].mean()
calibrated_brier = test["calibrated_squared_error"].mean()
improvement_pct = (market_brier - calibrated_brier) / market_brier * 100

print(f"\n--- Brier score (record-level, n={len(test)}) ---")
print(f"Raw market price Brier score:        {market_brier:.5f}")
print(f"Calibrated model Brier score:        {calibrated_brier:.5f}")
print(f"Improvement: {improvement_pct:.1f}% lower error (lower is better)")
