# test_triangles.py

from stonkslib.patterns.triangles import find_triangles

tickers = ["AAPL"]  # Add any tickers you want to test
intervals = ["1m", "15m", "1h", "1d"]

for ticker in tickers:
    for interval in intervals:
        print(f"🔍 Testing {ticker} ({interval})")
        patterns = find_triangles(ticker, interval)
        if patterns:
            print(f"✔️ Found {len(patterns)} patterns for {ticker} ({interval})")
        else:
            print(f"❌ No patterns found for {ticker} ({interval})")
