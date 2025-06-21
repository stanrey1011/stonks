import os
import pandas as pd
from project.utils import load_ticker_data
import yaml

def load_tickers_from_yaml():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    file_path = os.path.join(base_dir, "tickers.yaml")
    with open(file_path, "r") as f:
        data = yaml.safe_load(f)

    tickers = []
    for category in data.values():
        if isinstance(category, list):
            tickers.extend(category)
    return tickers

def main():
    tickers = load_tickers_from_yaml()
    for ticker in tickers:
        try:
            df = load_ticker_data(ticker)
            print(f"{ticker}: {df['Date'].min().date()} → {df['Date'].max().date()} | rows: {len(df)}")
        except Exception as e:
            print(f"{ticker}: Error loading data — {e}")

if __name__ == "__main__":
    main()
