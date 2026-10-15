"""
crypto_collect.py

For each 15-minute crypto market (most recent first), saves:
  - the price at minute 2, 5 and 10 inside the window (last trade by then)
  - the last trade of the whole market (the end-of-window price)
  - the outcome

Results are written to crypto_prices.csv after every market. You can stop it
any time with Ctrl+C and analyze what's saved (that's the kill switch).
Run it again later and it resumes where it stopped.

Change SERIES to collect ETH or SOL later (KXETH15M, KXSOL15M); each series
gets its own file.
"""

import csv
import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from kalshi_pull import fetch_full_history

SERIES = "KXBTC15M"
MAX_MARKETS = 4000          # stop after this many markets
MINUTES = [2, 5, 10]
BASE = "https://api.elections.kalshi.com/trade-api/v2"
CACHE_FILE = f"crypto_prices_{SERIES}.csv"
COLUMNS = ["ticker", "close_time", "outcome", "last_trade"] + [f"p{k}" for k in MINUTES]


def get_candles(ticker, start_ts, end_ts, is_old):
    params = {"start_ts": start_ts, "end_ts": end_ts, "period_interval": 1}
    regular = f"{BASE}/series/{SERIES}/markets/{ticker}/candlesticks"
    historical = f"{BASE}/historical/markets/{ticker}/candlesticks"
    urls = [historical, regular] if is_old else [regular, historical]
    for url in urls:
        for attempt in range(3):
            response = requests.get(url, params=params, timeout=20)
            if response.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            break
        if response.status_code == 200:
            return response.json().get("candlesticks", [])
    return None


def price_at(candles, cutoff_ts):
    best = None
    for c in candles:
        if c.get("end_period_ts", 0) > cutoff_ts:
            continue
        close = (c.get("price") or {}).get("close_dollars")
        if close not in (None, ""):
            best = float(close)
    return best


done = set()
if os.path.exists(CACHE_FILE):
    done = set(pd.read_csv(CACHE_FILE)["ticker"])
    print(f"Resuming: {len(done)} markets already saved in {CACHE_FILE}.")
else:
    with open(CACHE_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(COLUMNS)

print(f"Fetching the {SERIES} market list (both endpoints)...")
markets = fetch_full_history(series_ticker=SERIES, status="settled", verbose=False)
markets = [m for m in markets if m.get("result") in ("yes", "no") and m.get("close_time")]
markets.sort(key=lambda m: m["close_time"], reverse=True)   # most recent first
todo = [m for m in markets if m["ticker"] not in done][:MAX_MARKETS]
print(f"{len(markets)} settled markets available. Collecting {len(todo)} (most recent first).")
print("Press Ctrl+C at any time to stop. Everything collected so far is saved.\n")

now = datetime.now(timezone.utc)
request_failures = 0
rows_written = 0
with open(CACHE_FILE, "a", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    try:
        for i, m in enumerate(todo, start=1):
            close = pd.to_datetime(m["close_time"], format="ISO8601", utc=True)
            window_start = close - timedelta(minutes=15)
            start_ts = int((window_start - timedelta(minutes=1)).timestamp())
            end_ts = int(close.timestamp())
            is_old = close < now - timedelta(days=90)

            candles = get_candles(m["ticker"], start_ts, end_ts, is_old)
            time.sleep(0.15)
            if candles is None:
                request_failures += 1
                continue

            prices = []
            for k in MINUTES:
                cutoff = int((window_start + timedelta(minutes=k)).timestamp())
                p = price_at(candles, cutoff)
                prices.append("" if p is None else p)
            writer.writerow([m["ticker"], m["close_time"], 1 if m["result"] == "yes" else 0,
                             m.get("last_price_dollars", "")] + prices)
            f.flush()
            rows_written += 1
            if i % 100 == 0:
                print(f"  {i}/{len(todo)} processed (request failures: {request_failures})")
    except KeyboardInterrupt:
        print("\nStopped by you. Saved results are safe.")

print(f"\nDone. Rows written this run: {rows_written}. Request failures: {request_failures}.")
print(f"Now run: python crypto_analysis.py")
