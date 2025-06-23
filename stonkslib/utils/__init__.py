# stonkslib/utils/__init__.py

import os
import pandas as pd

def load_ticker_data(ticker: str, base_dir: str = "data/ticker_data", interval: str = "1d") -> pd.DataFrame:
    """
    Load ticker data from the CSV files stored in the ticker_data directory for the given interval.
    """
    # Construct the file path based on the ticker, base directory, and interval
    file_path = os.path.join(base_dir, interval, f"{ticker}.csv")
    
    # Check if the file exists and load it
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"{ticker}.csv not found in {base_dir}/{interval}")
    
    # Load and return the data
    return pd.read_csv(file_path, index_col=0, parse_dates=True)
