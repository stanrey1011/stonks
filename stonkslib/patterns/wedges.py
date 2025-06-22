"""
Detect falling and rising wedge patterns using local extrema and trendline slopes.
"""

import logging
import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
from sklearn.linear_model import LinearRegression
from stonkslib.utils import load_ticker_data

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def fit_trendline(points):
    if len(points) < 3:
        return None
    x = np.arange(len(points)).reshape(-1, 1)
    y = np.array(points).reshape(-1, 1)
    model = LinearRegression().fit(x, y)
    return model.coef_[0][0]  # slope

def find_wedge_patterns(ticker, category, interval, window=5, lookback=60):
    """
    Detect wedge chart patterns (falling and rising wedges) from OHLC data.

    Parameters:
        ticker (str): Ticker symbol
        category (str): Dataset category
        interval (str): Time interval
        window (int): Local extrema window
        lookback (int): Number of rows to analyze

    Returns:
        List of pattern tuples: (start_date, end_date, pattern_type, confidence)
    """
    try:
        df = load_ticker_data(ticker, category, interval)
    except FileNotFoundError as e:
        log.warning(f"[!] {e}")
        return []

    df = df.sort_index().copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"]).tail(lookback)

    if df.empty or "Close" not in df.columns:
        return []

    highs_idx = argrelextrema(df["Close"].values, np.greater_equal, order=window)[0]
    lows_idx = argrelextrema(df["Close"].values, np.less_equal, order=window)[0]

    highs = df.iloc[highs_idx]
    lows = df.iloc[lows_idx]

    if len(highs) < 3 or len(lows) < 3:
        return []

    upper_slope = fit_trendline(highs["Close"].values)
    lower_slope = fit_trendline(lows["Close"].values)

    pattern = None
    if upper_slope is not None and lower_slope is not None:
        if upper_slope < 0 and lower_slope < 0 and upper_slope > lower_slope:
            pattern = "Falling Wedge"
        elif upper_slope > 0 and lower_slope > 0 and upper_slope < lower_slope:
            pattern = "Rising Wedge"

    if pattern:
        start_date = df.iloc[min(highs_idx[0], lows_idx[0])].name
        end_date = df.iloc[max(highs_idx[-1], lows_idx[-1])].name
        slope_diff = abs((upper_slope or 0) - (lower_slope or 0))
        confidence = max(0, round(1.0 - min(slope_diff * 10, 1.0), 2))

        if confidence >= 0.4:
            return [(start_date, end_date, pattern, confidence)]

    return []
