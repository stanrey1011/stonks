"""
Detect head and shoulders / inverse head and shoulders patterns using local extrema.
"""

import logging
import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
from stonkslib.utils import load_ticker_data

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def find_head_shoulders_patterns(ticker, category, interval, window=5, lookback=60):
    """
    Detect head and shoulders or inverse head and shoulders patterns.

    Args:
        ticker (str): Ticker symbol
        category (str): Dataset category
        interval (str): Time interval
        window (int): Window for extrema detection
        lookback (int): How many rows to analyze

    Returns:
        List of pattern tuples (start_date, end_date, pattern_type, confidence)
    """
    try:
        df = load_ticker_data(ticker, category, interval)
    except FileNotFoundError as e:
        log.warning(f"[!] {e}")
        return []

    df = df.sort_index().copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"]).tail(lookback)

    if df.empty:
        return []

    extrema_idx = argrelextrema(df["Close"].values, np.greater_equal, order=window)[0]
    points = df.iloc[extrema_idx]

    patterns = []

    for i in range(len(points) - 4):
        p = points.iloc[i:i+5]
        vals = p["Close"].values

        # Normal Head and Shoulders: shoulder < head > shoulder
        if vals[0] < vals[1] and vals[1] < vals[2] and vals[3] < vals[2] and vals[4] < vals[3]:
            confidence = round(1.0 - abs(vals[1] - vals[3]) / vals[2], 2)
            if confidence >= 0.4:
                patterns.append((p.index[0], p.index[-1], "Head & Shoulders", confidence))

        # Inverse Head and Shoulders: shoulder > head < shoulder
        if vals[0] > vals[1] and vals[1] > vals[2] and vals[3] > vals[2] and vals[4] > vals[3]:
            confidence = round(1.0 - abs(vals[1] - vals[3]) / vals[2], 2)
            if confidence >= 0.4:
                patterns.append((p.index[0], p.index[-1], "Inverse Head & Shoulders", confidence))

    return patterns
