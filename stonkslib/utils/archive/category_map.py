# category_map.py

# Defines which timeframes should be fetched for each category of asset
CATEGORY_TIMEFRAME_MAP = {
    "stocks": ["1m", "2m", "5m", "15m", "30m", "1h", "1wk"],
    "etfs":   ["1m", "5m", "15m", "1h", "1wk"],
    "crypto": ["1h", "1wk", "1mo"]  # Excludes minute data due to Yahoo API limitations
}

# Defines the maximum number of days back allowed per interval
TIMEFRAME_LIMITS = {
    "1m":   7,     # Max ~7 days for 1-minute granularity
    "2m":   7,     # Max ~7 days for 2-minute granularity
    "5m":  30,     # Max ~30 days for 5-minute granularity
    "15m": 60,     # Max ~60 days for 15-minute granularity
    "30m": 60,     # Max ~60 days for 30-minute granularity
    "1h":  730,    # Max ~2 years
#    "1d":  1460,   # ~4 years
    "1wk": 260,    # ~5 years
    "1mo": 120     # ~10 years
}
