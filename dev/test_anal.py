# test_anal.py

from stonkslib.utils import load_ticker_data
from stonkslib.patterns.find_patterns import find_patterns

# Test parameters
ticker = "AAPL"
interval = "1d"  # Choose your interval, e.g., "1d", "1wk", etc.
base_dir = "data/ticker_data"

# Load the ticker data for the specified interval
ticker_data = load_ticker_data(ticker, base_dir=base_dir, interval=interval)

# Run pattern detection
patterns = find_patterns(ticker_data, interval)

# Print detected patterns
if patterns:
    for pattern in patterns:
        print(f"Pattern detected: {pattern['pattern_type']}")
else:
    print("No patterns detected.")
