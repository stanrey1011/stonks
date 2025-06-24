from pathlib import Path
import pandas as pd

def load_td(tickers: list[str], interval: str, lookback: int = 120, base_dir: str = "data/ticker_data/clean"):
#def load_td(category: str, interval: str, tickers: list, base_dir="data/ticker_data/clean"):
    """
    Load cleaned CSVs into memory for LLMs or analysis.

    Args:
        category (str): One of 'stocks', 'etfs', 'crypto'
        interval (str): Timeframe like '1d', '1wk', '1m'
        tickers (list): List of tickers to load
        base_dir (str): Path to the clean data directory

    Returns:
        dict: Dictionary of DataFrames keyed by ticker symbol
    """
    data = {}
    interval_path = Path(base_dir) / interval

    for ticker in tickers:
        file_path = interval_path / f"{ticker}.csv"
        if not file_path.exists():
            print(f"[!] Missing cleaned file: {ticker} ({interval})")
            continue

        df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        df = df.sort_index()
        data[ticker] = df.tail(lookback)

    return data

# Example usage
# data = load_td(category="stocks", interval="1d", tickers=["AAPL", "MSFT"])
# print(data["AAPL"].tail())
