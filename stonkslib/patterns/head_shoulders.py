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

def find_head_shoulders(ticker, interval, window=5):
    """
    Detect head and shoulders chart patterns from OHLC data.
    Uses the entire cleaned dataset.
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

    for i in range(1, len(highs_idx) - 1):
        left_shoulder = highs_idx[i - 1]
        head = highs_idx[i]
        right_shoulder = highs_idx[i + 1]

        l_close = df.iloc[left_shoulder]["Close"]
        h_close = df.iloc[head]["Close"]
        r_close = df.iloc[right_shoulder]["Close"]

        # Head must be higher than both shoulders
        if h_close > l_close and h_close > r_close:
            shoulder_diff = abs(l_close - r_close)
            if shoulder_diff < 0.05 * h_close:  # Shoulders within 5% of head
                # Find neckline between the two shoulders
                neck_range = lows_idx[(lows_idx > left_shoulder) & (lows_idx < right_shoulder)]
                if len(neck_range) == 0:
                    continue
                neck_line_min_idx = neck_range.min()
                neckline = df.iloc[neck_line_min_idx]["Close"]

                confidence = round(1.0 - shoulder_diff * 50, 2)
                if confidence >= 0.4:
                    patterns.append((
                        df.iloc[left_shoulder].name,
                        df.iloc[head].name,
                        df.iloc[right_shoulder].name,
                        "Head and Shoulders",
                        confidence
                    ))

    return patterns

if __name__ == "__main__":
    ticker = "AAPL"
    intervals = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]
    for interval in intervals:
        print(f"🔍 Checking {ticker} ({interval})...")
        patterns = find_head_shoulders(ticker, interval)
        if patterns:
            print(f"✔️ Found {len(patterns)} patterns for {ticker} ({interval})")
            for (left, head, right, pattern, confidence) in patterns:
                print(f"  🧑‍🎤 {pattern} from {left} to {right} with confidence {confidence}")
        else:
            print(f"❌ No patterns found for {ticker} ({interval})")
