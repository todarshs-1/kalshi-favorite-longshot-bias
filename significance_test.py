"""
significance_test.py

Tests whether each probability bucket's actual outcome rate is
STATISTICALLY significantly different from what the market implied --
not just "looks different," but different by more than chance would explain.

Method: Poisson-binomial z-test. Each market has its own implied probability
(not one shared probability), so we can't use a simple coin-flip binomial
test. Instead: expected wins = sum of each market's implied probability.
Variance = sum of each market's p*(1-p). Then z = (observed - expected) / sqrt(variance),
which is approximately normally distributed for a large sample (Central
Limit Theorem), letting us get a p-value.
"""

import math
import pandas as pd

df = pd.read_csv("kalshi_combined_settled.csv", encoding="latin-1")

df = df[df["result"].isin(["yes", "no"])].copy()
excluded_series = ["KXNBAPTS", "KXNBAREB"]
df = df[~df["series"].isin(excluded_series)].copy()
df["actual_outcome"] = (df["result"] == "yes").astype(int)

bins = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
df["bucket"] = pd.cut(df["implied_probability"], bins=bins, include_lowest=True)


def normal_cdf(z):
    """Standard normal cumulative distribution function, using math.erf
    (built into Python -- no need to install scipy just for this).
    """
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def poisson_binomial_ztest(implied_probs, outcomes):
    """Returns (observed, expected, z_score, p_value) for one bucket."""
    n = len(implied_probs)
    expected = implied_probs.sum()
    observed = outcomes.sum()
    variance = (implied_probs * (1 - implied_probs)).sum()

    if variance == 0:
        return observed, expected, None, None

    z = (observed - expected) / math.sqrt(variance)
    # Two-tailed p-value: probability of seeing a deviation this extreme
    # in EITHER direction, if the market were actually well-calibrated.
    p_value = 2 * (1 - normal_cdf(abs(z)))

    return observed, expected, z, p_value


print(f"{'Bucket':<15} {'n':>7} {'Observed':>10} {'Expected':>10} {'Z-score':>9} {'P-value':>12}")
print("-" * 68)

for bucket, group in df.groupby("bucket", observed=True):
    observed, expected, z, p_value = poisson_binomial_ztest(
        group["implied_probability"], group["actual_outcome"]
    )
    n = len(group)

    if z is None:
        print(f"{str(bucket):<15} {n:>7} {observed:>10.1f} {expected:>10.1f} {'n/a':>9} {'n/a':>12}")
    else:
        sig_flag = "***" if p_value < 0.001 else ("**" if p_value < 0.01 else ("*" if p_value < 0.05 else ""))
        print(f"{str(bucket):<15} {n:>7} {observed:>10.1f} {expected:>10.1f} {z:>9.2f} {p_value:>12.2e} {sig_flag}")

print("\n*** p<0.001   ** p<0.01   * p<0.05   (blank = not statistically significant)")
print("\nA large negative z-score means the market's longshots won FAR LESS")
print("often than implied -- overpriced, and unlikely to be due to chance.")
