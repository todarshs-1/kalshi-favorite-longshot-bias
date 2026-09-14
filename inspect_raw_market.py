"""
inspect_raw_market.py

Fetches ONE settled market straight from the API and prints every field it
has, with its value. We're hunting for the field that holds the LAST TRADED
price (a historical record) rather than the live bid/ask (which resets once
a market closes).
"""

from kalshi_pull import fetch_page

data = fetch_page(series_ticker="KXNBAGAME", status="settled", limit=1)
market = data["markets"][0]

print(f"Ticker: {market.get('ticker')}\n")
print("All fields on this market:\n")

for key, value in sorted(market.items()):
    print(f"  {key}: {value}")
