"""
pregame_price_test_full.py

Same clean test as pregame_price_test.py, but on MLB's FULL settled history
(2025 and 2026), with three upgrades:

  1. Results are saved to mlb_pregame_prices.csv as it runs. If it crashes or
     you stop it, run it again and it picks up where it left off.
  2. The significance test uses ONE row per game (the underdog side), because
     the two sides of a game are mirror images and shouldn't be counted twice.
  3. A split by year, to see if the pattern holds in both 2025 and 2026.

Expect roughly 30 to 45 minutes. Progress prints every 200 markets.
"""

import csv
import math
import os
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from kalshi_pull import fetch_full_history

SERIES = "KXMLBGAME"
CACHE_FILE = "mlb_pregame_prices.csv"
CUTOFF_MINUTES_BEFORE_START = 30
LOOKBACK_HOURS = 48
BASE = "https://api.elections.kalshi.com/trade-api/v2"

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}
PATTERN = re.compile(r"KXMLBGAME-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})")


def get_candles(ticker, start_ts, end_ts, is_old):
    params = {"start_ts": start_ts, "end_ts": end_ts, "period_interval": 60}
    regular = f"{BASE}/series/{SERIES}/markets/{ticker}/candlesticks"
    historical = f"{BASE}/historical/markets/{ticker}/candlesticks"
    urls = [historical, regular] if is_old else [regular, historical]
    for url in urls:
        for attempt in range(3):
            response = requests.get(url, params=params, timeout=20)
            if response.status_code == 429:  # rate limited: wait and retry
                time.sleep(2 * (attempt + 1))
                continue
            break
        if response.status_code == 200:
            return response.json().get("candlesticks", [])
    return None


def last_traded_price(candles, cutoff_ts):
    best = None
    for c in candles:
        if c.get("end_period_ts", 0) > cutoff_ts:
            continue
        close = (c.get("price") or {}).get("close_dollars")
        if close not in (None, ""):
            best = float(close)
    return best


def normal_p(z):
    return 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))


# ---------- 1. Load the cache, fetch whatever is still missing ----------
done = set()
if os.path.exists(CACHE_FILE):
    done = set(pd.read_csv(CACHE_FILE)["ticker"])
    print(f"Cache found: {len(done)} markets already collected.")
else:
    with open(CACHE_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["ticker", "pregame_price", "outcome"])

print("Fetching MLB market list (both endpoints)...")
markets = fetch_full_history(series_ticker=SERIES, status="settled", verbose=False)
todo = [m for m in markets if m.get("ticker") not in done and m.get("result") in ("yes", "no")
        and PATTERN.match(m.get("ticker", ""))]
print(f"{len(markets)} markets in total, {len(todo)} still to fetch.\n")

now = datetime.now(UTC)
failed = 0
no_price = 0
with open(CACHE_FILE, "a", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    for i, m in enumerate(todo, start=1):
        yy, mon, dd, hh, mm = PATTERN.match(m["ticker"]).groups()
        start_utc = datetime(2000 + int(yy), MONTHS[mon], int(dd), int(hh), int(mm), tzinfo=ET).astimezone(UTC)
        cutoff = start_utc - timedelta(minutes=CUTOFF_MINUTES_BEFORE_START)
        cutoff_ts = int(cutoff.timestamp())
        start_ts = int((cutoff - timedelta(hours=LOOKBACK_HOURS)).timestamp())
        is_old = start_utc < now - timedelta(days=90)

        candles = get_candles(m["ticker"], start_ts, cutoff_ts, is_old)
        time.sleep(0.15)
        if candles is None:
            failed += 1
        else:
            price = last_traded_price(candles, cutoff_ts)
            if price is None:
                no_price += 1
            else:
                writer.writerow([m["ticker"], price, 1 if m["result"] == "yes" else 0])
                f.flush()
        if i % 200 == 0:
            print(f"  {i}/{len(todo)} processed (failed: {failed}, no pre-game trades: {no_price})")

print(f"\nFetch finished. Failed requests: {failed}. No pre-game trades: {no_price}.\n")

# ---------- 2. Analysis ----------
df = pd.read_csv(CACHE_FILE)
df["event"] = df["ticker"].str.rsplit("-", n=1).str[0]
df["year"] = 2000 + df["ticker"].str.extract(r"KXMLBGAME-(\d{2})")[0].astype(int)
print(f"Markets with a pre-game price: {len(df)}")
print(df["pregame_price"].describe())

# One row per game: keep the UNDERDOG side (lower pre-game price).
games = df.sort_values("pregame_price").groupby("event").filter(lambda g: len(g) == 2)
underdogs = games.sort_values("pregame_price").groupby("event").head(1)
print(f"\nGames with both sides priced: {underdogs['event'].nunique()}")


def summarize(frame, label):
    n = len(frame)
    expected = frame["pregame_price"].sum()
    observed = frame["outcome"].sum()
    variance = (frame["pregame_price"] * (1 - frame["pregame_price"])).sum()
    z = (observed - expected) / math.sqrt(variance) if variance > 0 else float("nan")
    return {
        "group": label, "games": n,
        "avg_price": frame["pregame_price"].mean(),
        "actual_win_rate": frame["outcome"].mean(),
        "gap_points": (frame["outcome"].mean() - frame["pregame_price"].mean()) * 100,
        "expected_wins": expected, "observed_wins": observed,
        "z": z, "p": normal_p(z),
    }


rows = [summarize(underdogs, "ALL underdogs")]
for year, g in underdogs.groupby("year"):
    rows.append(summarize(g, f"Underdogs {year}"))
for lo, hi in [(0.0, 0.35), (0.35, 0.45), (0.45, 0.51)]:
    g = underdogs[(underdogs["pregame_price"] >= lo) & (underdogs["pregame_price"] < hi)]
    if len(g) > 0:
        rows.append(summarize(g, f"Underdogs priced {int(lo*100)}-{int(hi*100)}%"))

pd.set_option("display.width", 160)
pd.set_option("display.float_format", "{:.3f}".format)
print("\nUnderdog test (one row per game; negative gap = underdogs win LESS than priced):")
print(pd.DataFrame(rows).to_string(index=False))
