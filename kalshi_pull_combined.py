"""
kalshi_pull_combined.py

Pulls settled markets from several Kalshi series, tags each row with which
series it came from, computes implied probability from the yes bid/ask
midpoint, and saves everything into one combined CSV ready for analysis.

Requires kalshi_pull.py in the same folder (we reuse fetch_all_markets from it).
"""

import csv

from kalshi_pull import fetch_full_history

# Series confirmed to have real settled history (checked with check_series_sizes.py).
# Add more here later once you've verified they exist and aren't empty/looping.
SERIES_LIST = [
    "KXNBAGAME",
    "KXNBAPTS",
    "KXNBAREB",
    "KXMLBGAME",
    "KXHIGHNY",    # daily high temp, NYC
    "KXHIGHDEN",   # daily high temp, Denver
    "KXLOWTMIA",   # daily low temp, Miami
    "KXLOWTPHIL",  # daily low temp, Philadelphia
]


def compute_implied_probability(market):
    """Return the market's implied probability of 'yes', using the last
    traded price. Returns None if that price is missing/invalid.

    NOTE: We use last_price_dollars, NOT yes_bid_dollars/yes_ask_dollars.
    The bid/ask reflect the LIVE order book, which resets to a meaningless
    0/1 range once a market closes. last_price_dollars is a historical
    record of the actual last trade, so it survives settlement intact.
    """
    try:
        price = float(market.get("last_price_dollars"))
    except (TypeError, ValueError):
        return None

    return price


def pull_and_tag(series_ticker):
    """Fetch all settled markets for one series and tag each with its source
    series and computed implied probability.
    """
    markets = fetch_full_history(series_ticker=series_ticker, status="settled")

    for market in markets:
        market["series"] = series_ticker
        market["implied_probability"] = compute_implied_probability(market)

    return markets


def save_combined_csv(all_markets, filename):
    fields = [
        "series",
        "ticker",
        "title",
        "result",
        "implied_probability",
        "last_price_dollars",
        "volume_fp",
        "open_time",
        "close_time",
    ]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for market in all_markets:
            writer.writerow(market)

    print(f"\nSaved {len(all_markets)} total markets to {filename}")


if __name__ == "__main__":
    combined = []

    for series in SERIES_LIST:
        print(f"\n--- Pulling {series} ---")
        markets = pull_and_tag(series)
        combined.extend(markets)
        print(f"{series}: {len(markets)} markets pulled")

    save_combined_csv(combined, "kalshi_combined_settled.csv")

    print(f"\nTotal across all series: {len(combined)}")
