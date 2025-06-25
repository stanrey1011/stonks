# stonkslib/patterns/wedges.py

import logging
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
from stonkslib.utils.load_td import load_td
import warnings

# Suppress specific warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.2
PRICE_TOLERANCE = 0.02

def find_wedges(ticker, interval, window=5):
    """
    Detect wedge patterns from OHLC data and return a DataFrame.
    """
    try:
        df = load_td([ticker], interval)[ticker]
    except FileNotFoundError as e:
        log.warning(f"[!] {e}")
        return pd.DataFrame(columns=["start", "end", "pattern", "confidence"])

    df = df.sort_index().copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"])

    if df.empty or "Close" not in df.columns:
        return pd.DataFrame(columns=["start", "end", "pattern", "confidence"])

    highs_idx = argrelextrema(df["Close"].values, np.greater_equal, order=window)[0]
    lows_idx = argrelextrema(df["Close"].values, np.less_equal, order=window)[0]

    patterns = []

    # Rising wedge: series of lower highs
    for i in range(1, len(highs_idx)):
        a, b = highs_idx[i - 1], highs_idx[i]
        p1, p2 = df.iloc[a]["Close"], df.iloc[b]["Close"]
        pct_diff = abs(p1 - p2) / max(p1, p2)
        if pct_diff < PRICE_TOLERANCE:
            confidence = round(1.0 - pct_diff * 50, 2)
            if confidence >= CONFIDENCE_THRESHOLD:
                patterns.append((df.index[a], df.index[b], "Rising Wedge", confidence))

    # Falling wedge: series of higher lows
    for i in range(1, len(lows_idx)):
        a, b = lows_idx[i - 1], lows_idx[i]
        p1, p2 = df.iloc[a]["Close"], df.iloc[b]["Close"]
        pct_diff = abs(p1 - p2) / max(p1, p2)
        if pct_diff < PRICE_TOLERANCE:
            confidence = round(1.0 - pct_diff * 50, 2)
            if confidence >= CONFIDENCE_THRESHOLD:
                patterns.append((df.index[a], df.index[b], "Falling Wedge", confidence))

    return pd.DataFrame(patterns, columns=["start", "end", "pattern", "confidence"])

if __name__ == "__main__":
    ticker = "AAPL"
    intervals = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]

    for interval in intervals:
        print(f"🔍 Checking {ticker} ({interval})...")
        df = find_wedges(ticker, interval)
        if not df.empty:
            print(f"✔️ Found {len(df)} patterns")
            for _, row in df.iterrows():
                emoji = "⬆️" if row["pattern"] == "Rising Wedge" else "⬇️"
                print(f"  {emoji} {row['pattern']} from {row['start']} to {row['end']} with confidence {row['confidence']}")
        else:
            print("❌ No patterns found.")
