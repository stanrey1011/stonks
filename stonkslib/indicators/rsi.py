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

    # Align with original index
    rsi_series = rsi_series.reindex(df.index)

    return rsi_series


def generate_rsi_signals(series):
    """
    Generate RSI signals for overbought/oversold.
    Expects a Series (not a DataFrame).
    """
    if isinstance(series, pd.DataFrame):
        if series.shape[1] != 1:
            raise ValueError("generate_rsi_signals expects a Series or single-column DataFrame")
        series = series.iloc[:, 0]

    signals = []
    for i in range(1, len(series)):
        rsi_val = series.iloc[i]
        signal = ""
        if rsi_val > 70:
            signal = "🔼 Overbought"
        elif rsi_val < 30:
            signal = "🔽 Oversold"
        signals.append(signal)

    df = pd.DataFrame({
        "RSI": series.iloc[1:],
        "Signal": signals
    })
    return df[df["Signal"] != ""]


# Manual test
if __name__ == "__main__":
    from stonkslib.utils.load_td import load_td
    ticker = "AAPL"
    interval = "1d"

    df = load_td([ticker], interval)[ticker]
    rsi_series = rsi(df, period=14)

    rsi_signals = generate_rsi_signals(rsi_series)

    if rsi_signals.empty:
        print("No RSI signals")
    else:
        print(rsi_signals.tail())
