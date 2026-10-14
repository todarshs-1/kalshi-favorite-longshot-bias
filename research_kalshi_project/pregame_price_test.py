"""
pregame_price_test.py

The clean test. Instead of the LAST trade (which happens at the end of the
game, when the winner is known), this pulls each market's price from BEFORE
the game starts, using Kalshi's candlestick (price history) endpoint.

Steps for each MLB market:
  1. Decode the true start time from the ticker (e.g. 26SEP162138 = Sept 16, 21:38 ET).
  2. Set a cutoff 30 minutes before that start.
  3. Ask for hourly price candles ending at or before the cutoff.
  4. Use the last traded price in those candles as the pre-game price.
  5. Compare pre-game prices to what actually happened.
"""

import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from kalshi_pull import fetch_all_markets

SERIES = "KXMLBGAME"
CUTOFF_MINUTES_BEFORE_START = 30
LOOKBACK_HOURS = 48
BASE = "https://api.elections.kalshi.com/trade-api/v2"

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}
PATTERN = re.compile(r"KXMLBGAME-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})")


def get_candles(ticker, start_ts, end_ts):
    """Try the regular candlestick endpoint first, then the historical one."""
    params = {"start_ts": start_ts, "end_ts": end_ts, "period_interval": 60}
    urls = [
        f"{BASE}/series/{SERIES}/markets/{ticker}/candlesticks",
        f"{BASE}/historical/markets/{ticker}/candlesticks",
    ]
    for url in urls:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            return response.json().get("candlesticks", [])
    return None


def last_traded_price(candles, cutoff_ts):
    """Latest non-empty closing trade price in candles ending at/before the cutoff."""
    best = None
    for c in candles:
        if c.get("end_period_ts", 0) > cutoff_ts:
            continue
        close = (c.get("price") or {}).get("close_dollars")
        if close not in (None, ""):
            best = float(close)
    return best


markets = fetch_all_markets(series_ticker=SERIES, status="settled", max_pages=3, verbose=False)
print(f"Fetched {len(markets)} settled markets. Pulling pre-game prices (this takes a few minutes)...\n")

rows = []
failed_requests = 0
no_price = 0

for m in markets:
    match = PATTERN.match(m.get("ticker", ""))
    if not match or m.get("result") not in ("yes", "no"):
        continue
    yy, mon, dd, hh, mm = match.groups()
    start_utc = datetime(2000 + int(yy), MONTHS[mon], int(dd), int(hh), int(mm), tzinfo=ET).astimezone(UTC)
    cutoff = start_utc - timedelta(minutes=CUTOFF_MINUTES_BEFORE_START)
    cutoff_ts = int(cutoff.timestamp())
    start_ts = int((cutoff - timedelta(hours=LOOKBACK_HOURS)).timestamp())

    candles = get_candles(m["ticker"], start_ts, cutoff_ts)
    time.sleep(0.15)
    if candles is None:
        failed_requests += 1
        continue
    price = last_traded_price(candles, cutoff_ts)
    if price is None:
        no_price += 1
        continue
    rows.append({
        "ticker": m["ticker"],
        "pregame_price": price,
        "outcome": 1 if m["result"] == "yes" else 0,
    })

df = pd.DataFrame(rows)
print(f"Markets with a usable pre-game price: {len(df)}")
print(f"Requests that failed: {failed_requests}   No trades before cutoff: {no_price}\n")

if df.empty:
    print("No usable data. Paste this output back so we can adjust the endpoint settings.")
else:
    print("Distribution of pre-game prices:")
    print(df["pregame_price"].describe())

    bins = [0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0]
    df["bucket"] = pd.cut(df["pregame_price"], bins=bins, include_lowest=True)
    table = df.groupby("bucket", observed=True).agg(
        n=("outcome", "count"),
        avg_price=("pregame_price", "mean"),
        actual_rate=("outcome", "mean"),
    )
    table["difference"] = table["actual_rate"] - table["avg_price"]
    pd.set_option("display.float_format", "{:.3f}".format)
    print("\nPre-game calibration:")
    print(table)
