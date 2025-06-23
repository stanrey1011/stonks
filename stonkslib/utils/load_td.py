import os
import sys
import pandas as pd


def load_td(ticker, interval, base_dir="data/ticker_data"):
    """
    Load ticker data for a specific interval and ticker.

    Parameters:
        ticker (str): The ticker symbol (e.g., 'AAPL')
        interval (str): The time interval (e.g., 1d, 1m, etc.)
        base_dir (str): Base directory for ticker data

    Returns:
        pd.DataFrame: Loaded DataFrame
    """
    # Construct the file path
    file_path = os.path.join(base_dir, interval, f"{ticker}.csv")

    # Check if the file exists
    if not os.path.exists(file_path):
        print(f"❌ No data found for {ticker} at {file_path}")
        sys.exit(1)

    try:
        df = pd.read_csv(file_path, index_col=0)
        df.index = pd.to_datetime(df.index, utc=True, errors="coerce")
        df = df[df.index.notna()]
        print(f"✅ Loaded {len(df)} rows from {ticker} ({interval})")
        print(df.head())  # Optional, for debugging
        return df
    except Exception as e:
        print(f"❌ Failed to load {ticker} ({interval}): {e}")
        sys.exit(1)

# For testing (optional)
if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python load_td.py <ticker> <interval>")
        sys.exit(1)

    ticker = sys.argv[1]
    interval = sys.argv[2]
    load_td(ticker, interval)
