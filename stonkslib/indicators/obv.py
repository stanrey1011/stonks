# stonkslib/indicators/obv.py

import logging
import pandas as pd
import numpy as np
import warnings

# Suppress specific date warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def obv(df):
    """
    Calculate On-Balance Volume (OBV) for a given DataFrame.
    Returns a DataFrame with a single 'OBV' column.
    """
    df = df.copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")
    df = df.dropna(subset=["Close", "Volume"])

    direction = np.sign(df["Close"].diff()).fillna(0)
    obv_series = (direction * df["Volume"]).cumsum()
    return pd.DataFrame({"OBV": obv_series}, index=df.index)

# === Run standalone ===
if __name__ == "__main__":
    from stonkslib.utils.load_td import load_td
    ticker = "AAPL"
    interval = "1d"
    df = load_td([ticker], interval)[ticker]
    obv_df = obv(df)

    obv_df = obv_df.dropna(subset=["OBV"])

    if obv_df.empty or len(obv_df) < 2:
        print(f"[!] Not enough data to compute OBV for {ticker} ({interval})")
    else:
        latest = obv_df.iloc[-1]
        prev = obv_df.iloc[-2]
        direction = "🟢 Rising OBV (bullish)" if latest["OBV"] > prev["OBV"] else "🔴 Falling OBV (bearish)"
        print(obv_df.tail(10))
        print(f"\n{direction} — OBV: {latest['OBV']:.2f}")
