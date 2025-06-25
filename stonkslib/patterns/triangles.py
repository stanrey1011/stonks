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

CONFIDENCE_THRESHOLD = 0.2
PRICE_TOLERANCE = 0.02

def find_triangles(ticker, interval, window=5):
    """
    Detect triangle chart patterns (symmetrical, ascending, descending) and return as a DataFrame.
    """
    if not isinstance(interval, str):
        interval = str(interval)

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

    # Symmetrical triangles
    for i in range(len(highs_idx) - 1):
        a, b = highs_idx[i], highs_idx[i + 1]
        p1, p2 = df.iloc[a]["Close"], df.iloc[b]["Close"]
        pct_diff = abs(p1 - p2) / max(p1, p2)
        if pct_diff < PRICE_TOLERANCE:
            confidence = round(1.0 - pct_diff * 50, 2)
            if confidence >= CONFIDENCE_THRESHOLD:
                patterns.append((df.index[a], df.index[b], "Symmetrical Triangle", confidence))

    # Ascending triangles
    for i in range(len(lows_idx) - 1):
        a, b = lows_idx[i], lows_idx[i + 1]
        p1, p2 = df.iloc[a]["Close"], df.iloc[b]["Close"]
        pct_diff = abs(p1 - p2) / max(p1, p2)
        if pct_diff < PRICE_TOLERANCE:
            confidence = round(1.0 - pct_diff * 50, 2)
            if confidence >= CONFIDENCE_THRESHOLD:
                patterns.append((df.index[a], df.index[b], "Ascending Triangle", confidence))

    # Descending triangles
    for i in range(len(highs_idx) - 1):
        a, b = highs_idx[i], highs_idx[i + 1]
        if df.iloc[b]["Close"] < df.iloc[a]["Close"]:
            pct_diff = abs(df.iloc[b]["Close"] - df.iloc[a]["Close"]) / df.iloc[a]["Close"]
            confidence = round(1.0 - pct_diff * 50, 2)
            if confidence >= CONFIDENCE_THRESHOLD:
                patterns.append((df.index[a], df.index[b], "Descending Triangle", confidence))

    return pd.DataFrame(patterns, columns=["start", "end", "pattern", "confidence"])

if __name__ == "__main__":
    ticker = "AAPL"
    intervals = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]
    for interval in intervals:
        print(f"🔍 Checking {ticker} ({interval})...")
        df = find_triangles(ticker, interval)
        if not df.empty:
            print(f"✔️ Found {len(df)} patterns")
            for _, row in df.iterrows():
                emoji = "🔺" if "Ascending" in row["pattern"] else "🔻" if "Descending" in row["pattern"] else "🔼"
                print(f"  {emoji} {row['pattern']} from {row['start']} to {row['end']} with confidence {row['confidence']}")
        else:
            print("❌ No patterns found.")
