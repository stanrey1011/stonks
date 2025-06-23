# test_head_shoulders.py

from stonkslib.patterns.head_shoulders import find_head_shoulders

tickers = ["AAPL"]  # Add any tickers you want to test
intervals = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"]

for ticker in tickers:
    for interval in intervals:
        print(f"🔍 Testing {ticker} ({interval})")
        patterns = find_head_shoulders(ticker, interval)
        if patterns:
            print(f"✔️ Found {len(patterns)} patterns for {ticker} ({interval})")
        else:
            print(f"❌ No patterns found for {ticker} ({interval})")
