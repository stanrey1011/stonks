import logging
import pandas as pd
import numpy as np
import warnings
from stonkslib.utils.load_td import load_td  # Using load_td to load data

# Suppress the specific UserWarning related to date format inference
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def obv(ticker, interval, lookback=60):
    """
    Calculate On-Balance Volume (OBV) for a given ticker using data loaded via load_td.

    Parameters:
        ticker (str): Ticker symbol (must match CSV filename)
        interval (str): Time interval (e.g., '1d', '1m', etc.)
        lookback (int): Number of rows to load (default 60)

    Returns:
        pd.DataFrame: DataFrame with added 'OBV' column
    """
    # Ensure interval is a string
    if not isinstance(interval, str):
        raise ValueError(f"Expected 'interval' to be a string, but got {type(interval)}")

    df = load_td(ticker, interval, lookback=lookback)  # Load data using load_td

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
    interval = "1d"  # Ensure this is a string
    lookback = 60  # Default lookback
    obv_df = obv(ticker, interval, lookback=lookback)

    # Print the last 10 rows with relevant columns
    print(obv_df.tail(10)[["Close", "Volume", "OBV"]])
