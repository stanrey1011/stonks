import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

import os
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ticker_data")

def calculate_macd(ticker, short_window=12, long_window=26, signal_window=9):
    """
    Calculate MACD indicator for a given ticker's historical data CSV.

    Parameters:
        ticker (str): Ticker symbol, must match a CSV file in data/ticker_data/
        short_window (int): Period for the short-term EMA (default 12)
        long_window (int): Period for the long-term EMA (default 26)
        signal_window (int): Period for the signal line EMA (default 9)

    Returns:
        pd.DataFrame: Original data with additional columns:
                      'MACD', 'Signal_Line', 'Histogram'
    """

    file_path = os.path.join(DATA_DIR, f"{ticker}.csv")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CSV file for ticker '{ticker}' not found at {file_path}")

    df = pd.read_csv(file_path, parse_dates=["Date"])
    df.sort_values("Date", inplace=True)

    # ⬇️ Ensure Close is float and drop bad rows
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"])

    # Calculate EMAs
    ema_short = df["Close"].ewm(span=short_window, adjust=False).mean()
    ema_long = df["Close"].ewm(span=long_window, adjust=False).mean()

    # MACD line
    df["MACD"] = ema_short - ema_long

    # Signal line
    df["Signal_Line"] = df["MACD"].ewm(span=signal_window, adjust=False).mean()

    # Histogram (MACD - Signal)
    df["Histogram"] = df["MACD"] - df["Signal_Line"]

    return df

if __name__ == "__main__":
    # Quick test when running this script directly
    ticker = "AAPL"
    macd_df = calculate_macd(ticker)
    print(macd_df.tail(10)[["Date", "Close", "MACD", "Signal_Line", "Histogram"]])
