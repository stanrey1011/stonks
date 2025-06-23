# stonkslib/patterns/wedges.py

import logging
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
from stonkslib.utils.load_td import load_td
import sys
import warnings

# Suppress the specific UserWarning related to date format inference
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def find_wedges(ticker, interval, window=5, lookback=60):
    """
    Detect wedge chart patterns from OHLC data.
    
    This function identifies rising and falling wedge patterns based on the convergence of price action.
    """
    if not isinstance(interval, str):
        interval = str(interval)  # Ensure interval is a string

    try:
        # Load data using the updated load_ticker_data function
        df = load_td(ticker, base_dir="data/ticker_data", interval=interval)
    except FileNotFoundError as e:
        log.warning(f"[!] {e}")
        return []

    df = df.sort_index().copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"]).copy()
    df = df.tail(lookback)

    if df.empty or "Close" not in df.columns:
        return []

    # Identify local maxima and minima using the sliding window
    highs_idx = argrelextrema(df["Close"].values, np.greater_equal, order=window)[0]
    lows_idx = argrelextrema(df["Close"].values, np.less_equal, order=window)[0]

    patterns = []

    # Detecting rising wedge (lower highs and higher lows)
    for i in range(1, len(highs_idx)):
        a, b = highs_idx[i - 1], highs_idx[i]
        p1, p2 = df.iloc[a]["Close"], df.iloc[b]["Close"]
        pct_diff = abs(p1 - p2) / max(p1, p2)

        if pct_diff < 0.02:  # Threshold for local highs being close
            start = df.iloc[a].name
            end = df.iloc[b].name
            confidence = round(1.0 - pct_diff * 50, 2)
            if confidence >= 0.4:
                patterns.append((start, end, "Rising Wedge", confidence))

    # Detecting falling wedge (higher lows and lower highs)
    for i in range(1, len(lows_idx)):
        a, b = lows_idx[i - 1], lows_idx[i]
        p1, p2 = df.iloc[a]["Close"], df.iloc[b]["Close"]
        pct_diff = abs(p1 - p2) / max(p1, p2)

        if pct_diff < 0.02:  # Threshold for local lows being close
            start = df.iloc[a].name
            end = df.iloc[b].name
            confidence = round(1.0 - pct_diff * 50, 2)
            if confidence >= 0.4:
                patterns.append((start, end, "Falling Wedge", confidence))

    return patterns

# Optionally, run the function directly for testing
if __name__ == "__main__":
    ticker = "AAPL"
    intervals = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"]  # Add the intervals you want to test
    for interval in intervals:
        print(f"🔍 Testing {ticker} ({interval})")
        patterns = find_wedges(ticker, interval)
        if patterns:
            print(f"✔️ Found {len(patterns)} patterns for {ticker} ({interval})")
        else:
            print(f"❌ No patterns found for {ticker} ({interval})")
