"""
pull_historical.py

Fully paginates Kalshi's /historical/markets endpoint (not just one page)
to find out how far back real settled data actually goes. Uses the same
cursor-pagination pattern as fetch_all_markets, just pointed at a
different URL -- the max_close_ts filter turned out to be unreliable,
so we just page through everything and see where it naturally stops.
"""

import time
import requests

HISTORICAL_URL = "https://api.elections.kalshi.com/trade-api/v2/historical/markets"


def fetch_historical_page(series_ticker, cursor=None, limit=200):
    params = {"series_ticker": series_ticker, "limit": limit}
    if cursor:
        params["cursor"] = cursor

    response = requests.get(HISTORICAL_URL, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def fetch_all_historical(series_ticker, max_pages=100):
    all_markets = []
    cursor = None

    for page in range(max_pages):
        data = fetch_historical_page(series_ticker, cursor=cursor)
        markets = data.get("markets", [])
        if not markets:
            break

        all_markets.extend(markets)
        oldest_so_far = markets[-1].get("close_time")
        print(f"Page {page + 1}: got {len(markets)} (total: {len(all_markets)}) | oldest close_time so far: {oldest_so_far}")

        new_cursor = data.get("cursor")
        if not new_cursor or new_cursor == cursor:
            break
        cursor = new_cursor
        time.sleep(0.2)

    return all_markets


if __name__ == "__main__":
    markets = fetch_all_historical("KXHIGHNY")
    print(f"\nTotal historical markets found: {len(markets)}")
    if markets:
        print(f"Oldest close_time reached: {markets[-1].get('close_time')}")
        print(f"Newest close_time reached: {markets[0].get('close_time')}")
