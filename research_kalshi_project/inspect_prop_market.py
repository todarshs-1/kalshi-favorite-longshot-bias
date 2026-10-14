"""
inspect_prop_market.py

Pulls a handful of real settled KXNBAPTS markets and prints their key fields
side by side, so we can sanity-check by hand whether implied_probability
and result actually mean what we think they mean for prop/threshold markets
(as opposed to simple two-sided game-winner markets).
"""

from kalshi_pull import fetch_page

data = fetch_page(series_ticker="KXNBAPTS", status="settled", limit=10)
markets = data["markets"]

for m in markets:
    print(f"Ticker: {m.get('ticker')}")
    print(f"  Title: {m.get('title')}")
    print(f"  Rules (primary): {m.get('rules_primary')}")
    print(f"  last_price_dollars: {m.get('last_price_dollars')}")
    print(f"  previous_price_dollars: {m.get('previous_price_dollars')}")
    print(f"  result: {m.get('result')}")
    print(f"  volume_fp: {m.get('volume_fp')}")
    print(f"  yes_sub_title: {m.get('yes_sub_title')}")
    print()
