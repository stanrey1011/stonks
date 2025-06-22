import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

import os
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ticker_data")

def calculate_rsi(ticker, period=14):
    """
    Calculate RSI (Relative Strength Index) for a given ticker.

    Parameters:
        ticker (str): Ticker symbol matching the CSV filename.
        period (int): Number of periods to use for RSI calculation (default 14).

    Returns:
        pd.DataFrame: Original DataFrame with added 'RSI' column.
    """
    file_path = os.path.join(DATA_DIR, f"{ticker}.csv")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CSV for ticker '{ticker}' not found at {file_path}")

    df = pd.read_csv(file_path, parse_dates=["Date"])
    df.sort_values("Date", inplace=True)

    # Ensure 'Close' is numeric
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"])

    # Calculate price differences
    delta = df["Close"].diff()

    # Gains and losses
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Exponential Moving Averages of gains/losses
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    # RS and RSI
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))

    return df

if __name__ == "__main__":
    # Test the RSI function
    ticker = "AAPL"
    rsi_df = calculate_rsi(ticker)
    print(rsi_df.tail(10)[["Date", "Close", "RSI"]])
