import os
import pandas as pd
import numpy as np
import logging
from scipy.signal import argrelextrema
from sklearn.linear_model import LinearRegression

log = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ticker_data")

def fit_trendline(points):
    if len(points) < 3:
        return None, None
    x = np.arange(len(points)).reshape(-1, 1)
    y = np.array(points).reshape(-1, 1)
    model = LinearRegression().fit(x, y)
    return model.coef_[0][0], model.intercept_[0]  # slope, intercept

def detect_wedge_patterns(ticker, window=5, lookback=60, df=None):
    if df is None:
        file_path = os.path.join(DATA_DIR, f"{ticker}.csv")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"No data for {ticker}")
        df = pd.read_csv(file_path, parse_dates=["Date"])
        print(f"[DEBUG] Loaded {ticker}: {df.columns}")

    if "Date" not in df.columns or "Close" not in df.columns:
        raise ValueError(f"Required columns missing in data for {ticker}")

    df = df.sort_values("Date").copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"]).copy()
    df = df[-lookback:]

    highs_idx = argrelextrema(df["Close"].values, np.greater_equal, order=window)[0]
    lows_idx = argrelextrema(df["Close"].values, np.less_equal, order=window)[0]

    highs = df.iloc[highs_idx]
    lows = df.iloc[lows_idx]

    log.debug(f"Highs: {len(highs)} | Lows: {len(lows)}")

    if len(highs) < 3 or len(lows) < 3:
        return []

    upper_slope, _ = fit_trendline(highs["Close"].values)
    lower_slope, _ = fit_trendline(lows["Close"].values)

    log.debug(f"upper_slope={upper_slope:.4f}, lower_slope={lower_slope:.4f}")

    pattern = None
    if upper_slope < 0 and lower_slope < 0 and abs(upper_slope) > abs(lower_slope):
        pattern = "Falling Wedge"
    elif upper_slope > 0 and lower_slope > 0 and abs(lower_slope) > abs(upper_slope):
        pattern = "Rising Wedge"

    if pattern:
        slope_diff = abs((upper_slope or 0) - (lower_slope or 0))
        confidence = max(0, round(1.0 - min(slope_diff * 0.5, 1.0), 2))
        if confidence >= 0.2:
            start_date = df.iloc[min(highs_idx[0], lows_idx[0])]["Date"]
            end_date = df.iloc[max(highs_idx[-1], lows_idx[-1])]["Date"]
            return [(start_date, end_date, pattern, confidence)]

    return []

if __name__ == "__main__":
    ticker = "SPY"
    results = detect_wedge_patterns(ticker, lookback=120)
    if results:
        print(f"[{ticker}] Wedge Patterns:")
        for s, e, t, c in results:
            print(f" - {t} from {s.date()} to {e.date()} (confidence: {c})")
    else:
        print(f"[{ticker}] No wedge patterns detected.")
