# stonkslib/fetch/ranges.py

# Category to intervals and periods for yfinance
CATEGORY_INTERVALS = {
    "stocks": [
        ("1m", "7d"),
        ("2m", "60d"),
        ("5m", "60d"),
        ("15m", "45d"),
        ("30m", "45d"),
        ("1h", "2y"),
        ("1d", "10y"),
        ("1wk", "10y"),
    ],
    "etfs": [
        ("1m", "7d"),
        ("2m", "60d"),
        ("5m", "60d"),
        ("15m", "60d"),
        ("30m", "60d"),
        ("1h", "2y"),
        ("1d", "10y"),
        ("1wk", "10y"),
    ],
    "crypto": [
        ("1m", "7d"),
        ("2m", "60d"),
        ("5m", "60d"),
        ("15m", "60d"),
        ("30m", "60d"),
        ("1h", "2y"),
        ("1d", "10y"),
        ("1wk", "10y"),
    ],
}
