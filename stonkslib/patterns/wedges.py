# stonkslib/patterns/wedges.py

import logging
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
from stonkslib.utils.load_td import load_td
import warnings

# Suppress the specific UserWarning related to date format inference
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def find_wedges(ticker, interval, window=5):
    """
    Detect wedge chart patterns (rising/falling) from OHLC data.
    """
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

    # Detect rising wedge (lower highs)
    for i in range(1, len(highs_idx)):
        a, b = highs_idx[i - 1], highs_idx[i]
        p1, p2 = df.iloc[a]["Close"], df.iloc[b]["Close"]
        pct_diff = abs(p1 - p2) / max(p1, p2)
        if pct_diff < 0.02:
            confidence = round(1.0 - pct_diff * 50, 2)
            if confidence >= 0.4:
                patterns.append((df.index[a], df.index[b], "Rising Wedge", confidence))

    # Detect falling wedge (higher lows)
    for i in range(1, len(lows_idx)):
        a, b = lows_idx[i - 1], lows_idx[i]
        p1, p2 = df.iloc[a]["Close"], df.iloc[b]["Close"]
        pct_diff = abs(p1 - p2) / max(p1, p2)
        if pct_diff < 0.02:
            confidence = round(1.0 - pct_diff * 50, 2)
            if confidence >= 0.4:
                patterns.append((df.index[a], df.index[b], "Falling Wedge", confidence))

    return patterns

if __name__ == "__main__":
    ticker = "AAPL"
    intervals = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]

    for interval in intervals:
        print(f"🔍 Checking {ticker} ({interval})...")
        patterns = find_wedges(ticker, interval)
        if patterns:
            print(f"✔️ Found {len(patterns)} patterns for {ticker} ({interval})")
            for start, end, ptype, confidence in patterns:
                emoji = "⬆️" if ptype == "Rising Wedge" else "⬇️"
                print(f"  {emoji} {ptype} from {start} to {end} with confidence {confidence}")
        else:
            print(f"❌ No patterns found for {ticker} ({interval})")
