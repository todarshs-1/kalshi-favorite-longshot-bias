"""
crypto_analysis.py

Reads crypto_prices_KXBTC15M.csv (whatever has been collected so far) and, for
each measurement time, compares prices to what actually happened:

  - "end" = last trade of the whole market (the price we shouldn't trust)
  - minute 10, 5, 2 = prices from inside the window (the fair test)

Gap = actual win rate minus average price, in percentage points.
Negative gap in the cheap ranges and positive gap in the expensive ranges is
the favorite-longshot pattern. z and p say whether a gap is bigger than chance.
"""

import math

import pandas as pd

SERIES = "KXBTC15M"
FILE = f"crypto_prices_{SERIES}.csv"
CUTOFFS = [("end", "last_trade"), ("minute 10", "p10"), ("minute 5", "p5"), ("minute 2", "p2")]
BINS = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


def normal_p(z):
    return 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))


def stats(frame, col):
    n = len(frame)
    expected = frame[col].sum()
    observed = frame["outcome"].sum()
    variance = (frame[col] * (1 - frame[col])).sum()
    z = (observed - expected) / math.sqrt(variance) if variance > 0 else float("nan")
    return n, frame[col].mean(), frame["outcome"].mean(), (frame["outcome"].mean() - frame[col].mean()) * 100, z, normal_p(z)


df = pd.read_csv(FILE)
print(f"Rows collected so far: {len(df)}")
print(f"Window closing times from {df['close_time'].min()} to {df['close_time'].max()}")
print(f"Overall share of windows that resolved 'yes': {df['outcome'].mean():.1%}\n")

pd.set_option("display.width", 160)
pd.set_option("display.float_format", "{:.3f}".format)

for label, col in CUTOFFS:
    d = df.dropna(subset=[col]).copy()
    d = d[(d[col] > 0) & (d[col] < 1)]
    if len(d) < 50:
        print(f"=== {label}: too few usable rows ({len(d)}) ===\n")
        continue
    print(f"=== Price measured at: {label}   (rows: {len(d)}, average price {d[col].mean():.3f}, "
          f"actual yes rate {d['outcome'].mean():.3f}) ===")
    d["bucket"] = pd.cut(d[col], bins=BINS, include_lowest=True)
    rows = []
    for bucket, g in d.groupby("bucket", observed=True):
        n, avg, rate, gap, z, p = stats(g, col)
        rows.append({"price range": str(bucket), "n": n, "avg_price": avg,
                     "win_rate": rate, "gap_points": gap, "z": z, "p": p})
    print(pd.DataFrame(rows).to_string(index=False))
    cheap = d[d[col] <= 0.2]
    pricey = d[d[col] >= 0.8]
    for name, g in [("Cheap (<= 20%)", cheap), ("Expensive (>= 80%)", pricey)]:
        if len(g) > 0:
            n, avg, rate, gap, z, p = stats(g, col)
            print(f"  {name}: n={n}, avg price {avg:.3f}, win rate {rate:.3f}, gap {gap:+.2f} points, z={z:.2f}, p={p:.3f}")
    print()

print("Reminder: consecutive windows and different coins are not fully independent,")
print("so treat p-values as rough. Compare gap sizes to trading fees before calling anything 'tradeable'.")
