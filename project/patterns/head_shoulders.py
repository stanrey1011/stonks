import os
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ticker_data")

def detect_head_shoulders_patterns(ticker, window=10, inverse=False, df=None):
    if df is None:
        file_path = os.path.join(DATA_DIR, f"{ticker}.csv")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"CSV for ticker '{ticker}' not found at {file_path}")
        df = pd.read_csv(file_path, parse_dates=["Date"])
        print(f"[DEBUG] Loaded {ticker}: {df.columns}")

    if "Date" not in df.columns or "Close" not in df.columns:
        raise ValueError(f"Required columns missing in data for {ticker}")

    df = df.sort_values("Date").copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"]).copy()

    pattern_type = "Inverse H&S" if inverse else "Head & Shoulders"
    extrema_func = np.less_equal if inverse else np.greater_equal
    extrema_idx = argrelextrema(df["Close"].values, extrema_func, order=window)[0]

    patterns = []

    for i in range(len(extrema_idx) - 2):
        ls, head, rs = extrema_idx[i], extrema_idx[i+1], extrema_idx[i+2]
        p1, p2, p3 = df.iloc[ls]["Close"], df.iloc[head]["Close"], df.iloc[rs]["Close"]

        if inverse:
            if p2 < p1 and p2 < p3 and abs(p1 - p3) / max(p1, p3) < 0.05:
                confidence = 0.8 - (abs(p1 - p3) / max(p1, p3))
                patterns.append((df.iloc[ls]["Date"], df.iloc[rs]["Date"], pattern_type, round(confidence, 2)))
        else:
            if p2 > p1 and p2 > p3 and abs(p1 - p3) / max(p1, p3) < 0.05:
                confidence = 0.8 - (abs(p1 - p3) / max(p1, p3))
                patterns.append((df.iloc[ls]["Date"], df.iloc[rs]["Date"], pattern_type, round(confidence, 2)))

    return patterns

if __name__ == "__main__":
    ticker = "AAPL"
    patterns = detect_head_shoulders_patterns(ticker) + detect_head_shoulders_patterns(ticker, inverse=True)

    if patterns:
        print(f"[{ticker}] Patterns found:")
        for start, end, pattern_type, conf in patterns:
            print(f" - {pattern_type} from {start.date()} to {end.date()} (confidence: {conf})")
    else:
        print(f"[{ticker}] No patterns found.")
