"""
kalshi_pull.py

Pulls settled sports markets from Kalshi's public API and saves them to a CSV
for later analysis (e.g. a favorite-longshot bias study).

No API key needed -- Kalshi's market-READ endpoints are public.
You only need auth for trading/order placement, which this script doesn't do.

Usage:
    python kalshi_pull.py

Requires:
    pip install requests
"""

import csv
import time

import requests

MARKETS_URL = "https://api.elections.kalshi.com/trade-api/v2/markets"
HISTORICAL_URL = "https://api.elections.kalshi.com/trade-api/v2/historical/markets"


def fetch_page(base_url=MARKETS_URL, series_ticker=None, status="settled", cursor=None, limit=200):
    """Fetch one page of markets from Kalshi's API.

    base_url lets us point this at either the regular /markets endpoint
    (recent settled markets, last ~2-3 months) or /historical/markets
    (older archived markets). Same pagination logic works for both.

    Returns the parsed JSON response as a Python dict with 'markets' (a list)
    and 'cursor' (a string used to get the next page).
    """
    params = {"limit": limit}
    if status:
        params["status"] = status
    if series_ticker:
        params["series_ticker"] = series_ticker
    if cursor:
        params["cursor"] = cursor

    response = requests.get(base_url, params=params, timeout=10)
    response.raise_for_status()  # raise an exception on 4xx/5xx errors instead of failing silently
    return response.json()


def fetch_all_markets(series_ticker, base_url=MARKETS_URL, status="settled", max_pages=100, verbose=True):
    """Loop through every page of results using Kalshi's cursor pagination.

    Kalshi returns up to `limit` markets per call plus a 'cursor' string.
    Pass that cursor back in to get the next page. When the cursor stops
    changing (or comes back empty), we've reached the end of the data.
    """
    all_markets = []
    cursor = None

    for page in range(max_pages):
        data = fetch_page(base_url=base_url, series_ticker=series_ticker, status=status, cursor=cursor)
        markets = data.get("markets", [])
        if not markets:
            break

        all_markets.extend(markets)
        if verbose:
            oldest = markets[-1].get("close_time")
            print(f"  Page {page + 1}: got {len(markets)} (total so far: {len(all_markets)}) | oldest close_time: {oldest}")

        new_cursor = data.get("cursor")
        if not new_cursor or new_cursor == cursor:
            break
        cursor = new_cursor

        time.sleep(0.2)  # small delay to be polite to Kalshi's servers / avoid rate limits

    return all_markets


def fetch_full_history(series_ticker, status="settled", verbose=True):
    """Fetch a series' COMPLETE settled history by combining both endpoints:
    the regular /markets endpoint (recent, last ~2-3 months) and
    /historical/markets (everything older). Removes any overlapping
    duplicates by ticker, since the two endpoints' date ranges touch.
    """
    if verbose:
        print(f"  -- Recent markets (regular endpoint) --")
    recent = fetch_all_markets(series_ticker, base_url=MARKETS_URL, status=status, verbose=verbose)

    if verbose:
        print(f"  -- Older markets (historical endpoint) --")
    older = fetch_all_markets(series_ticker, base_url=HISTORICAL_URL, status=status, verbose=verbose)

    # Combine and de-duplicate by ticker (a dict keyed by ticker automatically
    # drops duplicates, since each ticker can only appear once as a key).
    combined = {m["ticker"]: m for m in older + recent}
    return list(combined.values())


def save_to_csv(markets, filename):
    """Save the fields relevant to a favorite-longshot study to a CSV file."""
    fields = [
        "ticker",
        "event_ticker",
        "title",
        "status",
        "result",
        "yes_bid_dollars",
        "yes_ask_dollars",
        "no_bid_dollars",
        "no_ask_dollars",
        "volume_fp",
        "open_time",
        "close_time",
    ]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for market in markets:
            writer.writerow(market)

    print(f"Saved {len(markets)} markets to {filename}")


if __name__ == "__main__":
    # KXNBAGAME = NBA game-winner markets. Swap for KXMLBGAME, KXNFLGAME, KXNHLGAME, etc.
    series = "KXNBAGAME"

    markets = fetch_full_history(series_ticker=series)
    save_to_csv(markets, f"{series}_settled.csv")
