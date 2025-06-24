import sys
import os

# Add stonkslib to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from stonkslib.utils.load_td import load_td

# Example usage
category = "stocks"
interval = "1d"
tickers = ["AAPL", "MSFT"]

data = load_td(category, interval, tickers)

for ticker, df in data.items():
    print(f"\n=== {ticker} ({len(df)} rows) ===")
    print(df.head())
