# stonkslib/indicators/rsi.py

import logging
import pandas as pd
import warnings

# Suppress format warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def rsi(df, period=14):
    """
    Calculate RSI (Relative Strength Index) for a DataFrame (expects 'Close' column).
    Returns a pandas Series with the RSI values.
    """
    df = df.copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"])

    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi_series = 100 - (100 / (1 + rs))

    # To ensure alignment with the input df's index:
    rsi_series = rsi_series.reindex(df.index)

    return rsi_series

# Manual test
if __name__ == "__main__":
    from stonkslib.utils.load_td import load_td
    ticker = "AAPL"
    interval = "1d"

    df = load_td([ticker], interval)[ticker]
    rsi_series = rsi(df, period=14)

    df["RSI"] = rsi_series
    rsi_df = df.dropna(subset=["RSI"])

    if rsi_df.empty:
        print(f"[!] Not enough data to compute RSI for {ticker} ({interval})")
    else:
        latest = rsi_df.iloc[-1]
        direction = "🔼 Overbought" if latest["RSI"] > 70 else (
                    "🔽 Oversold" if latest["RSI"] < 30 else "➡️ Neutral")

        print(rsi_df.tail(10)[["Close", "RSI"]])
        print(f"\n{direction} — Latest RSI: {latest['RSI']:.2f}")
