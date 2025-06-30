# stonkslib/fetch/ranges.py

from datetime import timedelta

# Category to intervals and periods for yfinance
CATEGORY_INTERVALS = {
    "stocks": [
        ("1m", "7d"),
        ("2m", "60d"),
        ("5m", "60d"),
        ("15m", "45d"),
        ("30m", "45d"),
        ("1h", "2y"),
        ("1d", "4y"),
        ("1wk", "5y"),
#        ("1mo", "5y"),
    ],
    "etfs": [
        ("1m", "7d"),
        ("2m", "60d"),
        ("5m", "60d"),
        ("15m", "60d"),
        ("30m", "60d"),
        ("1h", "2y"),
        ("1d", "4y"),
        ("1wk", "5y"),
#        ("1mo", "5y"),
    ],
    "crypto": [
        ("1m", "7d"),
        ("2m", "60d"),
        ("5m", "60d"),
        ("15m", "60d"),
        ("30m", "60d"),
        ("1h", "2y"),
        ("1d", "4y"),
        ("1wk", "5y"),
    ],
}

# Interval freshness policy — how recent the last candle must be
FRESHNESS_MAP = {
    "1m": timedelta(minutes=5),
    "2m": timedelta(minutes=10),
    "5m": timedelta(minutes=15),
    "15m": timedelta(minutes=30),
    "30m": timedelta(minutes=60),
    "1h": timedelta(hours=2),
    "1d": timedelta(days=1),
    "1wk": timedelta(weeks=1),
}
