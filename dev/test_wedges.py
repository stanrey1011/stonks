# test_wedges.py

from stonkslib.patterns.wedges import find_wedges

tickers = ["AAPL"]  # Add any tickers you want to test
intervals = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"]

for ticker in tickers:
    for interval in intervals:
        print(f"🔍 Testing {ticker} ({interval})")
        patterns = find_wedges(ticker, interval)
        if patterns:
            print(f"✔️ Found {len(patterns)} patterns for {ticker} ({interval})")
        else:
            print(f"❌ No patterns found for {ticker} ({interval})")
