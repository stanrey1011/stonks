# stonkslib/indicators/rsi.py

import logging
import pandas as pd
import warnings
from stonkslib.utils.load_td import load_td

# Suppress format warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# RSI Sensitivity Adjustments
# (period=7)     # More sensitive, short-term RSI
# (period=21)    # Smoother, long-term RSI

def rsi(ticker, interval, period=14):
    """
    Calculate RSI (Relative Strength Index) for a given ticker using clean data.

    Parameters:
        ticker (str): Ticker symbol
        interval (str): Time interval (e.g., '1d')
        period (int): RSI period (default 14)

    Returns:
        pd.DataFrame: DataFrame with 'RSI' column added
    """
    df_dict = load_td([ticker], interval)
    df = df_dict[ticker]

    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"])

    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))

    return df


# Example usage
if __name__ == "__main__":
    ticker = "AAPL"
    interval = "1d"

    rsi_df = rsi(ticker, interval)

    rsi_df = rsi_df.dropna(subset=["RSI"])
    if rsi_df.empty:
        print(f"[!] Not enough data to compute RSI for {ticker} ({interval})")
    else:
        latest = rsi_df.iloc[-1]
        direction = "🔼 Overbought" if latest["RSI"] > 70 else (
                    "🔽 Oversold" if latest["RSI"] < 30 else "➡️ Neutral")
        
        print(rsi_df.tail(10)[["Close", "RSI"]])
        print(f"\n{direction} — Latest RSI: {latest['RSI']:.2f}")
