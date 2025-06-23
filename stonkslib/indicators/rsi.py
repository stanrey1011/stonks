import logging
import pandas as pd
import warnings
from stonkslib.utils.load_td import load_td  # Using load_td to load data

# Suppress the specific UserWarning related to date format inference
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def rsi(ticker, interval, period=14, lookback=60):
    """
    Calculate RSI (Relative Strength Index) for a given ticker using data loaded via load_td.

    Parameters:
        ticker (str): Ticker symbol matching the CSV filename.
        interval (str): Time interval (e.g., '1d', '1m', etc.)
        period (int): Number of periods to use for RSI calculation (default 14).
        lookback (int): Number of rows to load (default 60).

    Returns:
        pd.DataFrame: Original DataFrame with added 'RSI' column.
    """
    df = load_td(ticker, interval, lookback=lookback)  # Load data using load_td

    # Convert Close to numeric (in case there are any non-numeric values)
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
    ticker = "AAPL"
    interval = "1d"  # Ensure this is a string
    lookback = 60  # Default lookback
    rsi_df = rsi(ticker, interval, lookback=lookback)

    # Print the last 10 rows with relevant columns, no need for 'Date' as a column
    print(rsi_df.tail(10)[["Close", "RSI"]])
