import logging
import pandas as pd
import warnings
from stonkslib.utils.load_td import load_td  # Using load_td to load data

# Suppress the specific UserWarning related to date format inference
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def macd(ticker, interval, short_window=12, long_window=26, signal_window=9, lookback=60):
    """Calculate MACD indicator"""
    df = load_td(ticker, interval, lookback)

    # Calculate EMAs
    ema_short = df["Close"].ewm(span=short_window, adjust=False).mean()
    ema_long = df["Close"].ewm(span=long_window, adjust=False).mean()

    # MACD line
    df["MACD"] = ema_short - ema_long

    # Signal line
    df["Signal_Line"] = df["MACD"].ewm(span=signal_window, adjust=False).mean()

    # Histogram (MACD - Signal)
    df["Histogram"] = df["MACD"] - df["Signal_Line"]

    # Debugging: Log the MACD columns
    logging.debug(f"MACD DataFrame for {ticker}: {df[['MACD', 'Signal_Line', 'Histogram']].tail()}")

    return df

if __name__ == "__main__":
    ticker = "AAPL"
    interval = "1d"  # Ensure this is a string
    lookback = 60  # Default lookback
    macd_df = macd(ticker, interval, lookback=lookback)

    # Print the last 10 rows with relevant columns, no need for 'Date' as a column
    print(macd_df.tail(10)[["Close", "MACD", "Signal_Line", "Histogram"]])
