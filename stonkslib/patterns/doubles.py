# stonkslib/patterns/doubles.py

import logging
import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
from stonkslib.utils.load_td import load_td
import warnings

# Suppress the specific UserWarning related to date format inference
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def find_doubles(ticker, interval, window=5):
    """
    Detect double top/bottom chart patterns from OHLC data.
    """
    try:
        df = load_td([ticker], interval)[ticker]
    except FileNotFoundError as e:
        log.warning(f"[!] {e}")
        return []

    df = df.sort_index().copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"])

    highs_idx = argrelextrema(df["Close"].values, np.greater_equal, order=window)[0]
    lows_idx = argrelextrema(df["Close"].values, np.less_equal, order=window)[0]

    patterns = []

    # Detect Double Top patterns
    for i in range(len(highs_idx) - 1):
        a, b = highs_idx[i], highs_idx[i + 1]
        p1, p2 = df.iloc[a]["Close"], df.iloc[b]["Close"]
        pct_diff = abs(p1 - p2) / max(p1, p2)
        if pct_diff < 0.02:
            start = df.iloc[a].name
            end = df.iloc[b].name
            confidence = round(1.0 - pct_diff * 50, 2)
            if confidence >= 0.4:
                patterns.append((start, end, "Double Top", confidence))

    # Detect Double Bottom patterns
    for i in range(len(lows_idx) - 1):
        a, b = lows_idx[i], lows_idx[i + 1]
        p1, p2 = df.iloc[a]["Close"], df.iloc[b]["Close"]
        pct_diff = abs(p1 - p2) / max(p1, p2)
        if pct_diff < 0.02:
            start = df.iloc[a].name
            end = df.iloc[b].name
            confidence = round(1.0 - pct_diff * 50, 2)
            if confidence >= 0.4:
                patterns.append((start, end, "Double Bottom", confidence))

    return patterns

if __name__ == "__main__":
    ticker = "AAPL"
    intervals = ["1d", "1h", "30m", "15m", "5m"]

    for interval in intervals:
        print(f"🔍 Checking {ticker} ({interval})...")
        results = find_doubles(ticker, interval)
        if results:
            print(f"✔️ Found {len(results)} patterns for {ticker} ({interval})")
            last = results[-1]
            emoji = "⬆️" if "Top" in last[2] else "⬇️"
            print(f"  {emoji} {last[2]} from {last[0]} to {last[1]} with confidence {last[3]}")
        else:
            print(f"❌ No patterns found for {ticker} ({interval})")
