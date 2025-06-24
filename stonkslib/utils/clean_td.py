# stonkslib/utils/clean_td.py

import os
import pandas as pd

# Base directory for locating data folders
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

def clean_td(ticker, interval, lookback=None, force=False, base_dir=BASE_DIR):
    """
    Load, clean, and return raw ticker data.
    Saves cleaned data to the appropriate location under `clean/`.

    Parameters:
        ticker (str): Ticker symbol (e.g. "AAPL")
        interval (str): Time interval (e.g. "1d", "1h")
        lookback (int): Number of recent rows to retain (optional)
        force (bool): Whether to overwrite existing clean files
        base_dir (str): Project base directory

    Returns:
        pd.DataFrame: Cleaned DataFrame
    """
    raw_path = os.path.join(base_dir, "data", "ticker_data", "raw", interval, f"{ticker}.csv")
    clean_path = os.path.join(base_dir, "data", "ticker_data", "clean", interval, f"{ticker}.csv")

    if not os.path.exists(raw_path):
        print(f"[!] No raw data found for {ticker} ({interval})")
        return

    try:
        df = pd.read_csv(raw_path, index_col=0)
        df.index = pd.to_datetime(df.index, utc=True, errors="coerce")
        df = df[df.index.notna()]
        df = df.sort_index()

        if lookback:
            df = df.tail(lookback)

        # Ensure index is named "Date" instead of default "Price"
        df.index.name = "Date"

        if not force and os.path.exists(clean_path):
            print(f"[⏭] Clean data already exists for {ticker} ({interval}) — skipping")
            return

        os.makedirs(os.path.dirname(clean_path), exist_ok=True)
        df.to_csv(clean_path)
        return df

    except Exception as e:
        print(f"[!] Failed to clean {ticker} ({interval}): {e}")
