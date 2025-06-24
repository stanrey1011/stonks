# stonkslib/indicators/obv.py

import logging
import pandas as pd
import numpy as np
import warnings
from stonkslib.utils.load_td import load_td

# Suppress specific date warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def obv(ticker, interval):
    """
    Calculate On-Balance Volume (OBV) for a given ticker using all available cleaned data.

    Parameters:
        ticker (str): Ticker symbol
        interval (str): Time interval (e.g., '1d', '1m')

    Returns:
        pd.DataFrame: DataFrame with added 'OBV' column
    """
    df_dict = load_td([ticker], interval)
    df = df_dict[ticker]

    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")
    df = df.dropna(subset=["Close", "Volume"])

    # Price change direction
    direction = np.sign(df["Close"].diff()).fillna(0)

    # OBV calculation
    df["OBV"] = (direction * df["Volume"]).cumsum()

    return df


# === Example parameter tweaks ===
# Use OBV on 1h data for intraday accumulation/distribution
# obv_df = obv("AAPL", "1h")

# Use OBV on 15m to track short-term pressure
# obv_df = obv("TSLA", "15m")

# === Run standalone ===
if __name__ == "__main__":
    ticker = "AAPL"
    interval = "1d"
    df = obv(ticker, interval)

    df = df.dropna(subset=["OBV"])

    if df.empty:
        print(f"[!] Not enough data to compute OBV for {ticker} ({interval})")
    else:
        latest = df.iloc[-1]
        direction = "🟢 Rising OBV (bullish)" if latest["OBV"] > df["OBV"].iloc[-2] else "🔴 Falling OBV (bearish)"
        print(df.tail(10)[["Close", "Volume", "OBV"]])
        print(f"\n{direction} — OBV: {latest['OBV']:.2f}")
