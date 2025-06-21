# project/utils.py

import os
import pandas as pd

DEBUG = False


# Set the base data directory relative to the project root
#DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ticker_data")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "ticker_data")

def load_ticker_data(ticker):
    file_path = os.path.join(DATA_DIR, f"{ticker}.csv")
    df = pd.read_csv(file_path, parse_dates=["Date"])
    if DEBUG:
        print(f"[DEBUG] Loaded {ticker}: {df.columns}")
    df = df.sort_values("Date")  # No .set_index
    return df


#def load_ticker_data(ticker):
    """
    Loads and cleans historical OHLCV data for a given ticker.
    
    - Skips header rows with repeated column names (from yfinance or other sources)
    - Parses the 'Date' column
    - Sorts and returns the DataFrame indexed by date
    """
#    file_path = os.path.join(DATA_DIR, f"{ticker}.csv")

#    if not os.path.exists(file_path):
#        raise FileNotFoundError(f"[ERROR] CSV for ticker '{ticker}' not found at {file_path}")

    # Skip second row with placeholder values (common in exported CSVs)
#    df = pd.read_csv(file_path, header=0, skiprows=[1], parse_dates=["Date"])

#    if "Date" not in df.columns or "Close" not in df.columns:
#        raise ValueError(f"[ERROR] Required columns missing in data for {ticker}: {df.columns.tolist()}")

#    df = df.sort_values("Date")
#    df.set_index("Date", inplace=True)
#    df = df[["Close", "Open", "High", "Low", "Volume"]]  # Optional: reorder or validate columns

#    return df
