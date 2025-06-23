import os
import sys
import pandas as pd

# Set the base directory to the root of your project
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

def load_td(ticker, interval, base_dir=BASE_DIR, lookback=60):
    """
    Load ticker data for a specific interval and ticker.
    
    Parameters:
        ticker (str): The ticker symbol (e.g., 'AAPL')
        interval (str): The time interval (e.g., '1d', '1m', etc.)
        base_dir (str): Base directory for ticker data (defaults to project root)
        lookback (int): Number of rows to load (default 60)

    Returns:
        pd.DataFrame: Loaded DataFrame
    """
    # Debug print to check if parameters are correct
    print(f"Debug - Base dir: {base_dir} (Type: {type(base_dir)})")
    print(f"Debug - Interval: {interval} (Type: {type(interval)})")
    print(f"Debug - Lookback: {lookback} (Type: {type(lookback)})")

    # Ensure interval is a string
    if not isinstance(interval, str):
        raise ValueError(f"Expected 'interval' to be a string, but got {type(interval)}")

    # Ensure lookback is an integer
    if not isinstance(lookback, int):
        raise ValueError(f"Expected 'lookback' to be an integer, but got {type(lookback)}")

    # Construct the file path
    file_path = os.path.join(base_dir, "data", "ticker_data", interval, f"{ticker}.csv")
    
    # Debugging output for file path
    print(f"Debug - File path: {file_path}")
    
    # Check if the file exists
    if not os.path.exists(file_path):
        print(f"❌ No data found for {ticker} at {file_path}")
        sys.exit(1)

    try:
        # Load the CSV file
        df = pd.read_csv(file_path, index_col=0)

        # Ensure that the index is a datetime object
        df.index = pd.to_datetime(df.index, utc=True, errors="coerce")

        # Drop any rows with invalid date/time
        df = df[df.index.notna()]

        # Log the number of rows loaded for the ticker and interval
        print(f"✅ Loaded {len(df)} rows from {ticker} ({interval})")
        print(df.head())  # Optional, for debugging

        # Limit data to lookback rows (most recent data)
        return df.tail(lookback)  # Use the most recent 'lookback' number of rows
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
