# stonkslib/patterns/doubles.py

import logging
import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
from stonkslib.utils.load_td import load_td
import warnings

# Suppress format warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

PRICE_TOLERANCE = 0.02
CONFIDENCE_THRESHOLD = 0.2

def find_doubles(ticker, interval, window=5):
    try:
        df = load_td([ticker], interval)[ticker]
    except FileNotFoundError as e:
        log.warning(f"[!] {e}")
        return pd.DataFrame(columns=["start", "end", "pattern", "confidence"])

    df = df.sort_index().copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"])

    highs_idx = argrelextrema(df["Close"].values, np.greater_equal, order=window)[0]
    lows_idx = argrelextrema(df["Close"].values, np.less_equal, order=window)[0]

    patterns = []

    for i in range(len(highs_idx) - 1):
        a, b = highs_idx[i], highs_idx[i + 1]
        p1, p2 = df.iloc[a]["Close"], df.iloc[b]["Close"]
        pct_diff = abs(p1 - p2) / max(p1, p2)
        if pct_diff < PRICE_TOLERANCE:
            confidence = round(1.0 - pct_diff * 50, 2)
            if confidence >= CONFIDENCE_THRESHOLD:
                patterns.append((df.index[a], df.index[b], "Double Top", confidence))

    for i in range(len(lows_idx) - 1):
        a, b = lows_idx[i], lows_idx[i + 1]
        p1, p2 = df.iloc[a]["Close"], df.iloc[b]["Close"]
        pct_diff = abs(p1 - p2) / max(p1, p2)
        if pct_diff < PRICE_TOLERANCE:
            confidence = round(1.0 - pct_diff * 50, 2)
            if confidence >= CONFIDENCE_THRESHOLD:
                patterns.append((df.index[a], df.index[b], "Double Bottom", confidence))

    return pd.DataFrame(patterns, columns=["start", "end", "pattern", "confidence"])

if __name__ == "__main__":
    ticker = "AAPL"
    intervals = ["1d", "1h", "30m", "15m", "5m"]
    for interval in intervals:
        print(f"🔍 Checking {ticker} ({interval})...")
        df = find_doubles(ticker, interval)
        if not df.empty:
            print(f"✔️ Found {len(df)} patterns")
            last = df.iloc[-1]
            emoji = "⬆️" if "Top" in last["pattern"] else "⬇️"
            print(f"  {emoji} {last['pattern']} from {last['start']} to {last['end']} with confidence {last['confidence']}")
        else:
            print(f"❌ No patterns found.")
