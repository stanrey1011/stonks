# stonkslib/patterns/pattern_wrapper.py

from stonkslib.patterns.doubles import find_double_patterns
from stonkslib.patterns.head_shoulders import find_head_shoulders_patterns
from stonkslib.patterns.triangles import find_triangle_patterns
from stonkslib.patterns.wedges import find_wedge_patterns

def find_patterns(tickers, category, intervals, lookback=60, window=5):
    """
    Detect patterns (double tops, head and shoulders, triangles, etc.) for all tickers and intervals.
    
    This function calls multiple pattern detection functions (e.g., find_double_patterns, etc.)
    for each ticker and interval, and aggregates the results.
    """
    all_patterns = []

    for ticker in tickers:
        for interval in intervals:
            # Run all pattern detection functions
            double_patterns = find_double_patterns(ticker, category, interval, window, lookback)
            head_shoulders = find_head_shoulders_patterns(ticker, category, interval, window, lookback)
            triangle_patterns = find_triangle_patterns(ticker, category, interval, window, lookback)
            wedge_patterns = find_wedge_patterns(ticker, category, interval, window, lookback)

            # Append all patterns
            all_patterns.extend(double_patterns)
            all_patterns.extend(head_shoulders)
            all_patterns.extend(triangle_patterns)
            all_patterns.extend(wedge_patterns)

    return all_patterns
