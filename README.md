# Kalshi favorite-longshot bias

Code for "Why the Last Trade Is the Wrong Price: Measuring Favorite-Longshot Bias on Kalshi" (Darsh Shah, 2026).

## Important: the first analysis was wrong
My first analysis used each market's last trade as its price. On game markets that
trade happens after the winner is known, so it created a fake bias. The calibration
model, the trading backtests, and the reported returns built on it are invalid.
Do not use them. They are kept in `archive/` only so the mistake can be inspected.

## Scripts to use
- `kalshi_pull.py`: shared helpers that download and combine Kalshi market data
- `verify_timing_assumption.py`: checks when game markets close (Section 4.2)
- `pregame_price_test_full.py`: MLB pre-game price test, writes mlb_pregame_prices.csv (Table 3)
- `crypto_feasibility.py`, `crypto_collect.py`: collect 15-minute Bitcoin market prices, writes crypto_prices_KXBTC15M.csv
- `crypto_analysis.py`: Bitcoin results (Table 4, Tables A1 and A2)

## Data files
- `mlb_pregame_prices.csv` and `crypto_prices_KXBTC15M.csv`: inputs and outputs of the scripts above
- `kalshi_combined_settled.csv`: the first-approach data (last-trade prices), read by the archived scripts

## Archived
`archive/bias_analysis.py` and `archive/significance_test.py` reproduce Tables 1 and 2,
the flawed last-trade result the paper explains. Run them from the project folder.
Everything else in `archive/` is either invalid or replaced by the scripts above.
