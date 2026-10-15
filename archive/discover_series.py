"""
discover_series.py

Asks Kalshi directly what series (recurring market templates) actually exist,
instead of us guessing ticker names. Prints ticker, title, category, and
frequency for each one so we can pick real, valid tickers to add to our pull.
"""

import requests

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2/series"


def get_series(category=None):
    params = {}
    if category:
        params["category"] = category

    response = requests.get(BASE_URL, params=params, timeout=10)
    response.raise_for_status()
    return response.json().get("series", [])


if __name__ == "__main__":
    # Check a few categories we're interested in. Kalshi's category names
    # are case-sensitive strings like "Sports", "Climate and Weather", etc --
    # we're not 100% sure of the exact spelling, so we'll print what comes
    # back (including an empty/no-filter call to see everything).
    categories_to_check = [None, "Sports", "Climate and Weather", "Weather", "Climate"]

    for category in categories_to_check:
        label = category if category else "(no filter -- all series)"
        print(f"\n=== Category: {label} ===")
        series_list = get_series(category=category)
        print(f"Found {len(series_list)} series")

        for s in series_list[:40]:  # cap at 40 so this stays readable
            print(f"  {s['ticker']:20s} | {s['frequency']:10s} | {s['title']}")
