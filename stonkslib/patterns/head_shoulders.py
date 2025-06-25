# stonkslib/patterns/head_shoulders.py

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
SHOULDER_TOLERANCE = 0.05  # 5%

def find_head_shoulders(ticker, interval, window=5):
    """
    Detect Head and Shoulders patterns from OHLC data and return as a DataFrame.
    """
    try:
        df = load_td([ticker], interval)[ticker]
    except FileNotFoundError as e:
        log.warning(f"[!] {e}")
        return pd.DataFrame(columns=["left", "head", "right", "pattern", "confidence"])

    df = df.sort_index().copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"])

    if df.empty or "Close" not in df.columns:
        return pd.DataFrame(columns=["left", "head", "right", "pattern", "confidence"])

    highs_idx = argrelextrema(df["Close"].values, np.greater_equal, order=window)[0]
    lows_idx = argrelextrema(df["Close"].values, np.less_equal, order=window)[0]

    patterns = []

    for i in range(1, len(highs_idx) - 1):
        left = highs_idx[i - 1]
        head = highs_idx[i]
        right = highs_idx[i + 1]

        l_close = df.iloc[left]["Close"]
        h_close = df.iloc[head]["Close"]
        r_close = df.iloc[right]["Close"]

        if h_close > l_close and h_close > r_close:
            shoulder_diff = abs(l_close - r_close)
            if shoulder_diff < SHOULDER_TOLERANCE * h_close:
                neck_range = lows_idx[(lows_idx > left) & (lows_idx < right)]
                if len(neck_range) == 0:
                    continue

                confidence = round(1.0 - shoulder_diff * 50, 2)
                if confidence >= CONFIDENCE_THRESHOLD:
                    patterns.append((
                        df.index[left],
                        df.index[head],
                        df.index[right],
                        "Head and Shoulders",
                        confidence
                    ))

    return pd.DataFrame(patterns, columns=["left", "head", "right", "pattern", "confidence"])

if __name__ == "__main__":
    ticker = "AAPL"
    intervals = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]
    for interval in intervals:
        print(f"🔍 Checking {ticker} ({interval})...")
        df = find_head_shoulders(ticker, interval)
        if not df.empty:
            print(f"✔️ Found {len(df)} patterns")
            for _, row in df.iterrows():
                print(f"  🧑‍🎤 {row['pattern']} from {row['left']} to {row['right']} with confidence {row['confidence']}")
        else:
            print("❌ No patterns found.")
