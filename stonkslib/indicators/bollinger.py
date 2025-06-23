# stonkslib/indicators/bollinger.py

import logging
import pandas as pd
from stonkslib.utils.load_td import load_td
import warnings

# Suppress the specific UserWarning related to date format inference
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def bollinger_bands(ticker, interval, window=20, num_std_dev=2, lookback=60):
    """
    Calculate Bollinger Bands for a given ticker using data loaded via load_td.
    """
    df = load_td(ticker, interval, lookback=lookback)  # Ensure correct order of parameters

    # Calculate rolling mean and std
    df["MA"] = df["Close"].rolling(window=window).mean()
    df["STD"] = df["Close"].rolling(window=window).std()

    df["Upper_Band"] = df["MA"] + (num_std_dev * df["STD"])
    df["Lower_Band"] = df["MA"] - (num_std_dev * df["STD"])

    return df

if __name__ == "__main__":
    ticker = "AAPL"
    interval = "1d"  # Make sure this is a string
    lookback = 60  # Correctly passing 'lookback' as the last argument
    bb_df = bollinger_bands(ticker, interval, lookback=lookback)

    # Print the last 10 rows with 'Date' from the index
    print(bb_df.tail(10)[["Close", "MA", "Upper_Band", "Lower_Band"]])  # No need for 'Date' as a column
