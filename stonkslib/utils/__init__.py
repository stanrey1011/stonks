import os
import pandas as pd

def _find_csv_for_ticker(ticker: str, base_dir: str = "data") -> str | None:
    for category in os.listdir(base_dir):
        path = os.path.join(base_dir, category, f"{ticker}.csv")
        if os.path.exists(path):
            return path
    return None

def load_ticker_data(ticker: str, base_dir: str = "data", interval: str = "1d") -> pd.DataFrame:
    csv_path = _find_csv_for_ticker(ticker, base_dir)
    if not csv_path:
        raise FileNotFoundError(f"{ticker}.csv not found in {base_dir}")
    return pd.read_csv(csv_path, index_col=0, parse_dates=True)
