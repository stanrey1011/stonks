# stonkslib/patterns/find_patterns.py

from stonkslib.patterns.doubles import find_double_patterns
from stonkslib.patterns.head_shoulders import find_head_shoulders_patterns
from stonkslib.patterns.triangles import find_triangle_patterns
from stonkslib.patterns.wedges import find_wedge_patterns


def find_patterns(tickers, intervals, lookback=60, window=5):
    """
    Detect patterns (double tops, head and shoulders, triangles, etc.) for all tickers and intervals.
    
    This function calls multiple pattern detection functions (e.g., find_double_patterns, etc.)
    for each ticker and interval, and aggregates the results.
    """
    all_patterns = []

    # Validate intervals to make sure they are strings
    if not all(isinstance(interval, str) for interval in intervals):
        raise TypeError(f"Expected 'intervals' to be a list of strings, but got {type(intervals)}")

    for ticker in tickers:
        for interval in intervals:
            # Ensure interval is a string (debug print to check if it's correct)
            if isinstance(interval, tuple):  # If interval is passed as a tuple (e.g. ('1', 'd'))
                interval = ''.join(interval)  # Concatenate the parts to form '1d', '1m', etc.
            print(f"Debug - Interval passed: {interval} (Type: {type(interval)})")  # Debug print

            if not isinstance(interval, str):
                raise TypeError(f"Expected 'interval' to be a string, but got {type(interval)}")

            # Run all pattern detection functions
            double_patterns = find_double_patterns(ticker, interval, window, lookback)
            head_shoulders = find_head_shoulders_patterns(ticker, interval, window, lookback)
            triangle_patterns = find_triangle_patterns(ticker, interval, window, lookback)
            wedge_patterns = find_wedge_patterns(ticker, interval, window, lookback)

            # Append all patterns
            all_patterns.extend(double_patterns)
            all_patterns.extend(head_shoulders)
            all_patterns.extend(triangle_patterns)
            all_patterns.extend(wedge_patterns)

    return all_patterns
