"""
Prints date span and row count for each ticker in a given interval.
"""

import os
import yaml
import logging
from stonkslib.utils import load_ticker_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def load_tickers():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yaml_path = os.path.join(base_dir, "tickers.yaml")
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)
    return [ticker for group in data.values() for ticker in group]

def main(interval="1d"):
    tickers = load_tickers()

    for ticker in tickers:
        try:
            df = load_ticker_data(ticker, interval=interval)
            start = df["Date"].min().date()
            end = df["Date"].max().date()
            logging.info(f"{ticker}: {start} → {end} | rows: {len(df)}")
        except Exception as e:
            logging.info(f"{ticker}: Error loading data — {e}")

if __name__ == "__main__":
    main()
