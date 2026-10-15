"""
crypto_feasibility.py  (Checkpoint 1 of the crypto experiment)

Answers three questions in about a minute:
  1. What do the 15-minute BTC markets actually look like in Kalshi's data?
     (We print raw fields, because we don't want to assume again.)
  2. Can we get 1-minute price history for them?
  3. Can we read a price from a FIXED minute inside each 15-minute window
     (minute 0, 5, 10), instead of the last trade at the very end?

PASS rule: at least 90% of sampled markets have a usable price at minute 5.
If it fails, we stop and submit the current paper as it is.
"""

import time
from datetime import timedelta

import pandas as pd
import requests

from kalshi_pull import fetch_all_markets

SERIES = "KXBTC15M"
BASE = "https://api.elections.kalshi.com/trade-api/v2"
SAMPLE_SIZE = 40
MINUTES_TO_TEST = [0, 5, 10]


def get_candles(ticker, start_ts, end_ts):
    params = {"start_ts": start_ts, "end_ts": end_ts, "period_interval": 1}
    urls = [
        f"{BASE}/series/{SERIES}/markets/{ticker}/candlesticks",
        f"{BASE}/historical/markets/{ticker}/candlesticks",
    ]
    for url in urls:
        response = requests.get(url, params=params, timeout=20)
        if response.status_code == 200:
            return response.json().get("candlesticks", [])
    return None


def price_at(candles, cutoff_ts):
    """Last traded price (closing price of a 1-minute candle) at or before cutoff_ts."""
    best = None
    for c in candles:
        if c.get("end_period_ts", 0) > cutoff_ts:
            continue
        close = (c.get("price") or {}).get("close_dollars")
        if close not in (None, ""):
            best = float(close)
    return best


markets = fetch_all_markets(series_ticker=SERIES, status="settled", max_pages=2, verbose=False)
print(f"Fetched {len(markets)} settled {SERIES} markets.\n")
if not markets:
    raise SystemExit("No markets returned. Paste this output back.")

print("--- Raw fields of the first 3 markets (so we can see what they really are) ---")
for m in markets[:3]:
    for key in ["ticker", "title", "yes_sub_title", "rules_primary", "strike_type",
                "floor_strike", "cap_strike", "open_time", "close_time",
                "result", "last_price_dollars", "volume_fp"]:
        print(f"  {key}: {m.get(key)}")
    print()

step = max(1, len(markets) // SAMPLE_SIZE)
sample = markets[::step][:SAMPLE_SIZE]
print(f"Testing price history on {len(sample)} sampled markets...\n")

rows = []
no_history = 0
for m in sample:
    if m.get("result") not in ("yes", "no"):
        continue
    close = pd.to_datetime(m["close_time"], format="ISO8601", utc=True)
    window_start = close - timedelta(minutes=15)
    start_ts = int((window_start - timedelta(minutes=5)).timestamp())
    end_ts = int(close.timestamp())
    candles = get_candles(m["ticker"], start_ts, end_ts)
    time.sleep(0.2)
    if not candles:
        no_history += 1
        continue
    row = {"ticker": m["ticker"], "outcome": 1 if m["result"] == "yes" else 0}
    for k in MINUTES_TO_TEST:
        cutoff = int((window_start + timedelta(minutes=k)).timestamp())
        row[f"price_min{k}"] = price_at(candles, cutoff)
    rows.append(row)

df = pd.DataFrame(rows)
print(f"Markets with any candle history: {len(df)} of {len(sample)} (no history: {no_history})\n")

if df.empty:
    print("RESULT: FAIL. No price history available. Stop and submit the current paper.")
else:
    for k in MINUTES_TO_TEST:
        col = f"price_min{k}"
        share = df[col].notna().mean()
        print(f"Minute {k:>2}: usable price for {share:.0%} of sampled markets")
    print("\nMinute-5 price distribution (usable ones):")
    print(df["price_min5"].describe())
    print(f"\nShare of sampled windows that resolved 'yes': {df['outcome'].mean():.1%}")
    verdict = "PASS" if df["price_min5"].notna().mean() >= 0.90 else "FAIL"
    print(f"\nCHECKPOINT 1 RESULT: {verdict} (needs 90% of markets with a minute-5 price)")
