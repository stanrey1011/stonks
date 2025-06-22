import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

import os
import pandas as pd
import numpy as np

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ticker_data")

def calculate_obv(ticker):
    """
    Calculate On-Balance Volume (OBV) for a given ticker.

    Parameters:
        ticker (str): Ticker symbol (must match CSV filename)

    Returns:
        pd.DataFrame: DataFrame with added 'OBV' column
    """
    file_path = os.path.join(DATA_DIR, f"{ticker}.csv")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CSV file for ticker '{ticker}' not found at {file_path}")

    df = pd.read_csv(file_path, parse_dates=["Date"])
    df.sort_values("Date", inplace=True)

    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")
    df = df.dropna(subset=["Close", "Volume"])

    # Price change direction
    direction = np.sign(df["Close"].diff()).fillna(0)
    
    # OBV logic
    df["OBV"] = (direction * df["Volume"]).cumsum()

    return df

if __name__ == "__main__":
    ticker = "AAPL"
    obv_df = calculate_obv(ticker)
    print(obv_df.tail(10)[["Date", "Close", "Volume", "OBV"]])
