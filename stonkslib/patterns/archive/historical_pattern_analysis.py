# @pattern_module: false

"""
Scans historical data for each ticker to identify chart patterns.
Allows interval selection (e.g., 1d, 1h, etc.)
"""

import os
import logging
import yaml
from stonkslib.utils import load_ticker_data
from stonkslib.patterns.doubles import find_double_patterns
from stonkslib.patterns.triangles import find_triangle_patterns
from stonkslib.patterns.wedges import find_wedge_patterns
from stonkslib.patterns.head_shoulders import find_head_shoulders_patterns

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def load_tickers():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yaml_path = os.path.join(base_dir, "tickers.yaml")
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)
    return [ticker for group in data.values() for ticker in group]

def scan_ticker(ticker, interval="1w"):
    try:
        df = load_ticker_data(ticker, interval=interval)
    except Exception as e:
        logging.info(f"{ticker}: Error loading data — {e}")
        return None

    patterns = []

    for detector in [find_double_top_bottom, find_triangles, find_wedges, find_head_shoulders_patterns]:
        found = detector(df, ticker)
        if found:
            patterns.extend(found)

    return patterns

def main(interval="1w"):
    tickers = load_tickers()
    any_found = False

    for ticker in tickers:
        logging.info(f"[↑] Running historical pattern scan for {ticker}")
        patterns = scan_ticker(ticker, interval=interval)

        if patterns:
            for p in patterns:
                print(p)
            any_found = True
        else:
            logging.info(f"[ℹ] No patterns found for {ticker}")

    if not any_found:
        logging.info("[!] No results written.")

if __name__ == "__main__":
    main()
