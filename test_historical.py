"""
test_historical.py

Checks whether Kalshi's /historical/markets endpoint gives us data older
than what the regular /markets endpoint returns. We test this on KXHIGHNY
(weather), since that series has existed since ~2021, unlike most of our
sports series which are new this year.
"""

import datetime
import requests

HISTORICAL_URL = "https://api.elections.kalshi.com/trade-api/v2/historical/markets"


def unix_timestamp(days_ago):
    """Convert 'N days ago from now' into a Unix timestamp (seconds).
    The API's time filters expect Unix timestamps, not calendar dates,
    so we need this conversion.
    """
    dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)
    return int(dt.timestamp())


def fetch_historical_page(series_ticker, max_close_ts=None, cursor=None, limit=200):
    params = {"series_ticker": series_ticker, "limit": limit}
    if max_close_ts:
        params["max_close_ts"] = max_close_ts
    if cursor:
        params["cursor"] = cursor

    response = requests.get(HISTORICAL_URL, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    one_year_ago = unix_timestamp(365)
    print(f"Requesting markets that closed before: {datetime.datetime.fromtimestamp(one_year_ago, tz=datetime.timezone.utc)}\n")

    data = fetch_historical_page("KXHIGHNY", max_close_ts=one_year_ago)
    markets = data.get("markets", [])

    print(f"Got {len(markets)} markets closing before one year ago")

    if markets:
        print(f"\nFirst market's real close_time field: {markets[0].get('close_time')}")
        print(f"Last market's real close_time field:  {markets[-1].get('close_time')}")
    else:
        print("\nNo markets found this far back through this endpoint/series.")

    # Control test: call the SAME endpoint with NO filter at all, and compare.
    # If the results are identical, the max_close_ts filter is being ignored.
    print("\n--- Control test: same call, no date filter ---")
    control_data = fetch_historical_page("KXHIGHNY")
    control_markets = control_data.get("markets", [])
    print(f"Got {len(control_markets)} markets with no filter")
    if control_markets:
        print(f"First market's real close_time field: {control_markets[0].get('close_time')}")
        print(f"Last market's real close_time field:  {control_markets[-1].get('close_time')}")

    same_first_ticker = markets and control_markets and markets[0]["ticker"] == control_markets[0]["ticker"]
    print(f"\nFiltered and unfiltered calls returned the same first ticker: {same_first_ticker}")
    print("(If True, the max_close_ts filter is likely being ignored.)")
