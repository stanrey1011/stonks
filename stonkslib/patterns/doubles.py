"""
Detect double top and double bottom patterns using local extrema.
"""

import logging
import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
from stonkslib.utils import load_ticker_data

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def find_double_patterns(ticker, category, interval, window=5, lookback=60):
    """
    Detect double top/bottom chart patterns from OHLC data.

    Parameters:
        ticker (str): Ticker symbol
        category (str): Dataset category (stocks, crypto, etfs)
        interval (str): Time interval (e.g., 1d, 1m)
        window (int): Local extrema window
        lookback (int): Number of recent rows to evaluate

    Returns:
        List of pattern tuples: (start_date, end_date, pattern_type, confidence_score)
    """
    try:
        df = load_ticker_data(ticker, category, interval)
    except FileNotFoundError as e:
        log.warning(f"[!] {e}")
        return []

    df = df.sort_index().copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"]).copy()
    df = df.tail(lookback)

    if df.empty or "Close" not in df.columns:
        return []

    highs_idx = argrelextrema(df["Close"].values, np.greater_equal, order=window)[0]
    lows_idx = argrelextrema(df["Close"].values, np.less_equal, order=window)[0]

    patterns = []

    # Detect double tops
    for i in range(len(highs_idx) - 1):
        a, b = highs_idx[i], highs_idx[i + 1]
        p1, p2 = df.iloc[a]["Close"], df.iloc[b]["Close"]
        pct_diff = abs(p1 - p2) / max(p1, p2)

        if pct_diff < 0.02:  # within 2%
            start = df.iloc[a].name
            end = df.iloc[b].name
            confidence = round(1.0 - pct_diff * 50, 2)
            if confidence >= 0.4:
                patterns.append((start, end, "Double Top", confidence))

    # Detect double bottoms
    for i in range(len(lows_idx) - 1):
        a, b = lows_idx[i], lows_idx[i + 1]
        p1, p2 = df.iloc[a]["Close"], df.iloc[b]["Close"]
        pct_diff = abs(p1 - p2) / max(p1, p2)

        if pct_diff < 0.02:
            start = df.iloc[a].name
            end = df.iloc[b].name
            confidence = round(1.0 - pct_diff * 50, 2)
            if confidence >= 0.4:
                patterns.append((start, end, "Double Bottom", confidence))

    return patterns
