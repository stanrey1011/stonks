# stonkslib/patterns/triangles.py

import logging
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
from stonkslib.utils.load_td import load_td
import warnings

warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def find_triangles(ticker, interval, window=5):
    """
    Detect triangle chart patterns from OHLC data.
    Identifies symmetrical, ascending, and descending triangle patterns.
    """
    if not isinstance(interval, str):
        interval = str(interval)

    try:
        df = load_td([ticker], interval)[ticker]
    except FileNotFoundError as e:
        log.warning(f"[!] {e}")
        return []

    df = df.sort_index().copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"])

    if df.empty or "Close" not in df.columns:
        return []

    highs_idx = argrelextrema(df["Close"].values, np.greater_equal, order=window)[0]
    lows_idx = argrelextrema(df["Close"].values, np.less_equal, order=window)[0]

    patterns = []

    # Symmetrical triangles
    for i in range(len(highs_idx) - 1):
        a, b = highs_idx[i], highs_idx[i + 1]
        p1, p2 = df.iloc[a]["Close"], df.iloc[b]["Close"]
        pct_diff = abs(p1 - p2) / max(p1, p2)
        if pct_diff < 0.02:
            start, end = df.index[a], df.index[b]
            confidence = round(1.0 - pct_diff * 50, 2)
            if confidence >= 0.4:
                patterns.append((start, end, "Symmetrical Triangle", confidence))

    # Ascending triangles
    for i in range(len(lows_idx) - 1):
        a, b = lows_idx[i], lows_idx[i + 1]
        p1, p2 = df.iloc[a]["Close"], df.iloc[b]["Close"]
        pct_diff = abs(p1 - p2) / max(p1, p2)
        if pct_diff < 0.02:
            start, end = df.index[a], df.index[b]
            confidence = round(1.0 - pct_diff * 50, 2)
            if confidence >= 0.4:
                patterns.append((start, end, "Ascending Triangle", confidence))

    # Descending triangles
    for i in range(len(highs_idx) - 1):
        a, b = highs_idx[i], highs_idx[i + 1]
        if df.iloc[b]["Close"] < df.iloc[a]["Close"]:
            start, end = df.index[a], df.index[b]
            confidence = round(1.0 - abs(df.iloc[b]["Close"] - df.iloc[a]["Close"]) / df.iloc[a]["Close"], 2)
            if confidence >= 0.4:
                patterns.append((start, end, "Descending Triangle", confidence))

    return patterns

if __name__ == "__main__":
    ticker = "AAPL"
    intervals = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]
    for interval in intervals:
        print(f"🔍 Checking {ticker} ({interval})...")
        patterns = find_triangles(ticker, interval)
        if patterns:
            print(f"✔️ Found {len(patterns)} patterns for {ticker} ({interval})")
            for start, end, pattern, confidence in patterns:
                emoji = "🔺" if "Ascending" in pattern else "🔻" if "Descending" in pattern else "🔼"
                print(f"  {emoji} {pattern} from {start} to {end} with confidence {confidence}")
        else:
            print(f"❌ No patterns found for {ticker} ({interval})")
