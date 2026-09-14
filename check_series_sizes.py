"""
check_series_sizes.py

Quick diagnostic: checks how many SETTLED markets exist for several different
Kalshi series, so we can see which ones have enough history to actually
analyze. Doesn't save anything -- just prints counts.
"""

from kalshi_pull import fetch_all_markets

# A mix of game-winner series and player-prop series across a few sports.
series_to_check = [
    "KXNBAGAME",
    "KXNBAREB",
    "KXMLBGAME",
]
print("Checking settled-market counts across series...\n")

results = {}
for series in series_to_check:
    markets = fetch_all_markets(series_ticker=series, status="settled")
    results[series] = len(markets)
    print(f"{series}: {len(markets)} settled markets\n")

print("Summary:")
for series, count in results.items():
    print(f"  {series}: {count}")
