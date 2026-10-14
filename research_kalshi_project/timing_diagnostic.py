"""
timing_diagnostic.py

Tests a specific concern: are game-winner markets' "last trade" prices
genuine PRE-GAME forecasts, or could they reflect information revealed
DURING the game (i.e., trading continuing until the outcome is already
essentially known)?

We check this using two timestamps every market has: occurrence_datetime
(the scheduled start of the game) and close_time (when the market actually
stopped trading). If close_time is close to occurrence_datetime, trading
stopped near game start -- consistent with a genuine pre-game forecast.
If close_time is hours later, trading continued deep into (or through)
the game, and last-trade prices may partly reflect the game's actual
progress rather than a clean advance prediction.
"""

import pandas as pd
from kalshi_pull import fetch_full_history

SERIES_TO_CHECK = ["KXNBAGAME", "KXMLBGAME"]

for series in SERIES_TO_CHECK:
    print(f"\n=== {series} ===")
    # Use fetch_full_history (both endpoints combined) rather than just the
    # recent endpoint -- otherwise an off-season series (e.g. NBA in
    # September) returns zero results even though real historical data exists.
    markets = fetch_full_history(series_ticker=series, status="settled", verbose=False)

    rows = []
    for m in markets:
        occurrence = m.get("occurrence_datetime")
        close = m.get("close_time")
        if not occurrence or not close:
            continue
        rows.append({
            "ticker": m.get("ticker"),
            "occurrence_datetime": occurrence,
            "close_time": close,
            "last_price_dollars": m.get("last_price_dollars"),
        })

    if not rows:
        print(f"WARNING: no usable rows found among {len(markets)} markets fetched.")
        if markets:
            print("Raw keys available on the first market fetched:")
            print(sorted(markets[0].keys()))
            print("\nFirst market's occurrence_datetime and close_time values:")
            print(f"  occurrence_datetime: {markets[0].get('occurrence_datetime')!r}")
            print(f"  close_time: {markets[0].get('close_time')!r}")
        continue

    df = pd.DataFrame(rows)
    df["occurrence_datetime"] = pd.to_datetime(df["occurrence_datetime"], format="ISO8601")
    df["close_time"] = pd.to_datetime(df["close_time"], format="ISO8601")
    df["gap_minutes"] = (df["close_time"] - df["occurrence_datetime"]).dt.total_seconds() / 60

    print(f"Markets checked: {len(df)}")
    print("\nGap between scheduled game start and market close (minutes):")
    print(df["gap_minutes"].describe())

    print("\n--- 5 example markets ---")
    print(df[["ticker", "occurrence_datetime", "close_time", "gap_minutes", "last_price_dollars"]].head())
