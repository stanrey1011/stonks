# stonkslib/patterns/head_shoulders.py

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

def find_head_shoulders(ticker, interval, window=5, lookback=60):
    """
    Detect head and shoulders chart patterns from OHLC data.
    
    This function identifies left shoulder, head, right shoulder, and neckline.
    """
    if not isinstance(interval, str):
        interval = str(interval)  # Ensure interval is a string

    try:
        # Load data using the updated load_ticker_data function
        df = load_td(ticker, interval)
    except FileNotFoundError as e:
        log.warning(f"[!] {e}")
        return []

    df = df.sort_index().copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"]).copy()
    df = df.tail(lookback)

    if df.empty or "Close" not in df.columns:
        return []

    # Identify local maxima (peaks) and minima (troughs)
    highs_idx = argrelextrema(df["Close"].values, np.greater_equal, order=window)[0]
    lows_idx = argrelextrema(df["Close"].values, np.less_equal, order=window)[0]

    patterns = []

    # Iterate over peaks to find head and shoulders pattern
    for i in range(1, len(highs_idx) - 1):
        left_shoulder = highs_idx[i - 1]
        head = highs_idx[i]
        right_shoulder = highs_idx[i + 1]

        # Ensure that the head is higher than the shoulders
        if df.iloc[head]["Close"] > df.iloc[left_shoulder]["Close"] and df.iloc[head]["Close"] > df.iloc[right_shoulder]["Close"]:
            # Ensure the left and right shoulders are similar in height
            shoulder_diff = abs(df.iloc[left_shoulder]["Close"] - df.iloc[right_shoulder]["Close"])
            if shoulder_diff < 0.05 * df.iloc[head]["Close"]:  # Relax the threshold for shoulder similarity to 5%
                # Confirm neckline (low points between shoulders)
                neck_line_min_idx = min(lows_idx[(lows_idx > left_shoulder) & (lows_idx < right_shoulder)])
                neckline = df.iloc[neck_line_min_idx]["Close"]

                confidence = round(1.0 - shoulder_diff * 50, 2)  # Confidence is based on shoulder similarity

                log.info(f"Pattern found: Left Shoulder: {df.iloc[left_shoulder]['Close']}, Head: {df.iloc[head]['Close']}, Right Shoulder: {df.iloc[right_shoulder]['Close']}, Neckline: {neckline}")
                
                if confidence >= 0.4:
                    patterns.append((df.iloc[left_shoulder].name, df.iloc[head].name, df.iloc[right_shoulder].name, "Head and Shoulders", confidence))

    return patterns

# Optionally, run the function directly for testing
if __name__ == "__main__":
    ticker = "AAPL"
    intervals = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"]  # Add the intervals you want to test
    for interval in intervals:
        print(f"🔍 Testing {ticker} ({interval})")
        patterns = find_head_shoulders(ticker, interval)
        if patterns:
            print(f"✔️ Found {len(patterns)} patterns for {ticker} ({interval})")
        else:
            print(f"❌ No patterns found for {ticker} ({interval})")
