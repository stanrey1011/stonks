import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

import os
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ticker_data")

def calculate_bollinger_bands(ticker, window=20, num_std_dev=2):
    """
    Calculate Bollinger Bands for a given ticker.

    Parameters:
        ticker (str): Ticker symbol (matches filename in ticker_data)
        window (int): Moving average window size (default 20)
        num_std_dev (float): Number of standard deviations (default 2)

    Returns:
        pd.DataFrame: DataFrame with added columns: 'MA', 'Upper_Band', 'Lower_Band'
    """
    file_path = os.path.join(DATA_DIR, f"{ticker}.csv")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CSV for ticker '{ticker}' not found at {file_path}")

    df = pd.read_csv(file_path, parse_dates=["Date"])
    df.sort_values("Date", inplace=True)

    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"])

    # Calculate rolling mean and std
    df["MA"] = df["Close"].rolling(window=window).mean()
    df["STD"] = df["Close"].rolling(window=window).std()

    df["Upper_Band"] = df["MA"] + (num_std_dev * df["STD"])
    df["Lower_Band"] = df["MA"] - (num_std_dev * df["STD"])

    return df

if __name__ == "__main__":
    ticker = "AAPL"
    bb_df = calculate_bollinger_bands(ticker)
    print(bb_df.tail(10)[["Date", "Close", "MA", "Upper_Band", "Lower_Band"]])
