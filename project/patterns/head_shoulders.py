import os
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ticker_data")

def detect_head_shoulders_patterns(ticker, window=10, inverse=False):
    """
    Detect (inverse) head and shoulders patterns in price data.

    Parameters:
        ticker (str): The ticker symbol.
        window (int): Window for local extrema detection.
        inverse (bool): If True, look for inverse H&S (bullish).

    Returns:
        List of (start_date, end_date, confidence_score, pattern_type)
    """
    file_path = os.path.join(DATA_DIR, f"{ticker}.csv")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CSV for ticker '{ticker}' not found at {file_path}")

    df = pd.read_csv(file_path, parse_dates=["Date"])
    df.sort_values("Date", inplace=True)
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"])

    pattern_type = "Inverse H&S" if inverse else "Head & Shoulders"
    extrema_func = np.less_equal if inverse else np.greater_equal
    extrema_idx = argrelextrema(df["Close"].values, extrema_func, order=window)[0]

    patterns = []

    for i in range(len(extrema_idx) - 2):
        ls, head, rs = extrema_idx[i], extrema_idx[i+1], extrema_idx[i+2]

        p1, p2, p3 = df.iloc[ls]["Close"], df.iloc[head]["Close"], df.iloc[rs]["Close"]

        if inverse:
            # Head should be lower than shoulders
            if p2 < p1 and p2 < p3 and abs(p1 - p3) / max(p1, p3) < 0.05:
                confidence = 0.8 - (abs(p1 - p3) / max(p1, p3))
                patterns.append((df.iloc[ls]["Date"], df.iloc[rs]["Date"], pattern_type, round(confidence, 2)))
        else:
            # Head should be higher than shoulders
            if p2 > p1 and p2 > p3 and abs(p1 - p3) / max(p1, p3) < 0.05:
                confidence = 0.8 - (abs(p1 - p3) / max(p1, p3))
                patterns.append((df.iloc[ls]["Date"], df.iloc[rs]["Date"], pattern_type, round(confidence, 2)))

    return patterns

if __name__ == "__main__":
    ticker = "AAPL"
    all_patterns = detect_head_shoulders(ticker) + detect_head_shoulders(ticker, inverse=True)

    if all_patterns:
        print(f"[{ticker}] Patterns found:")
        for start, end, conf, pattern_type in all_patterns:
            print(f" - {pattern_type} from {start.date()} to {end.date()} (confidence: {conf})")
    else:
        print(f"[{ticker}] No patterns found.")
