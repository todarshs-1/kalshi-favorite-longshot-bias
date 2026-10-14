"""
verify_timing_assumption.py

Earlier we assumed occurrence_datetime was the scheduled game START.
MLB tickers embed a start time (for example 26SEP162138 means Sept 16, 21:38
Eastern). This script decodes that start time and measures:

  1. occurrence_datetime minus the ticker start time
  2. close_time minus the ticker start time

If (1) is a steady ~180 minutes, occurrence_datetime is the EXPECTED END of
the game. If (2) is about 150-190 minutes, markets stay open DURING the game
and close when it ends, so the last trade happens when the result is known.
"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from kalshi_pull import fetch_all_markets

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}
PATTERN = re.compile(r"KXMLBGAME-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})")

markets = fetch_all_markets(series_ticker="KXMLBGAME", status="settled", max_pages=3, verbose=False)

rows = []
for m in markets:
    match = PATTERN.match(m.get("ticker", ""))
    if not match or not m.get("occurrence_datetime") or not m.get("close_time"):
        continue
    yy, mon, dd, hh, mm = match.groups()
    start_et = datetime(2000 + int(yy), MONTHS[mon], int(dd), int(hh), int(mm), tzinfo=ET)
    start_utc = start_et.astimezone(UTC)
    occurrence = pd.to_datetime(m["occurrence_datetime"], format="ISO8601", utc=True)
    close = pd.to_datetime(m["close_time"], format="ISO8601", utc=True)
    rows.append({
        "ticker": m["ticker"],
        "occurrence_minus_start": (occurrence - start_utc).total_seconds() / 60,
        "close_minus_start": (close - start_utc).total_seconds() / 60,
        "last_price": float(m.get("last_price_dollars") or 0),
    })

df = pd.DataFrame(rows)
print(f"Markets checked: {len(df)}\n")

print("occurrence_datetime minus ticker start time (minutes):")
print(df["occurrence_minus_start"].describe())

print("\nclose_time minus ticker start time (minutes):")
print(df["close_minus_start"].describe())

extreme = ((df["last_price"] <= 0.02) | (df["last_price"] >= 0.98)).mean()
print(f"\nShare of last-trade prices at 2 cents or below, or 98 cents or above: {extreme:.1%}")
