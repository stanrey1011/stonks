import os
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ticker_data")

def detect_double_patterns(ticker, window=5, type="top"):
    """
    Detect double top/bottom patterns in price data.

    Parameters:
        ticker (str): The ticker symbol
        window (int): Extrema detection window
        type (str): "top" or "bottom"

    Returns:
        List of (start_date, end_date, confidence_score, pattern_type)
    """
    file_path = os.path.join(DATA_DIR, f"{ticker}.csv")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CSV for ticker '{ticker}' not found.")

    df = pd.read_csv(file_path, parse_dates=["Date"])
    df.sort_values("Date", inplace=True)
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"])

    is_top = type == "top"
    extrema_func = np.greater_equal if is_top else np.less_equal
    extrema_idx = argrelextrema(df["Close"].values, extrema_func, order=window)[0]

    patterns = []
    pattern_name = "Double Top" if is_top else "Double Bottom"

    for i in range(len(extrema_idx) - 1):
        i1, i2 = extrema_idx[i], extrema_idx[i+1]
        p1, p2 = df.iloc[i1]["Close"], df.iloc[i2]["Close"]

        # Similar price within 5% tolerance
        if abs(p1 - p2) / max(p1, p2) < 0.05:
            # Days apart must be reasonable (not back to back)
            days_apart = (df.iloc[i2]["Date"] - df.iloc[i1]["Date"]).days
            if 10 <= days_apart <= 60:
                confidence = round(0.8 - (abs(p1 - p2) / max(p1, p2)), 2)
                start_date = df.iloc[i1]["Date"]
                end_date = df.iloc[i2]["Date"]
                patterns.append((start_date, end_date, pattern_name, confidence))

    return patterns

if __name__ == "__main__":
    ticker = "AAPL"
    patterns = detect_double_patterns(ticker, type="top") + detect_double_patterns(ticker, type="bottom")

    if patterns:
        print(f"[{ticker}] Double Top/Bottom Patterns:")
        for s, e, c, label in patterns:
            print(f" - {label} from {s.date()} to {e.date()} (confidence: {c})")
    else:
        print(f"[{ticker}] No double top/bottom patterns found.")
