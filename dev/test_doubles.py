# test_doubles.py

from stonkslib.patterns.doubles import find_doubles

tickers = ["AAPL"]  # Add any tickers you want to test
intervals = ["1d", "15m", "1m"]

for ticker in tickers:
    for interval in intervals:
        print(f"🔍 Testing {ticker} ({interval})")
        patterns = find_doubles(ticker, interval)
        if patterns:
            print(f"✔️ Found {len(patterns)} patterns for {ticker} ({interval})")
        else:
            print(f"❌ No patterns found for {ticker} ({interval})")
