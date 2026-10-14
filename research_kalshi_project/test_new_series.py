"""
test_new_series.py

Checks real settled-market counts for candidate series before we commit
to adding them to the full combined pull. Same verify-first habit we've
used throughout this project.
"""

from kalshi_pull import fetch_all_markets

candidates = [
    # Weather -- daily frequency, should have solid settled history
    "KXHIGHNY",
    "KXHIGHDEN",
    "KXLOWCHI",
    "KXLOWTMIA",
    "KXLOWTPHIL",
    "HIGHAUS",
    "KXLOWAUS",
    # Additional sports -- checking if they're actually in-season/active
    "KXNCAAFGAME",
    "KXPBAGAME",
    "KXUAEPLGAME",
]

print("Checking settled-market counts for candidate series...\n")

results = {}
for series in candidates:
    markets = fetch_all_markets(series_ticker=series, status="settled")
    results[series] = len(markets)
    print(f"{series}: {len(markets)} settled markets\n")

print("Summary:")
for series, count in sorted(results.items(), key=lambda x: -x[1]):
    print(f"  {series}: {count}")
