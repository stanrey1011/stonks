# stonkslib/merge/by_indicators.py

import os
import pandas as pd
from pathlib import Path
import logging

from stonkslib.utils.load_td import load_td

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_BASE = PROJECT_ROOT / "data" / "analysis" / "signals"
OUTPUT_BASE = PROJECT_ROOT / "data" / "analysis" / "merged" / "by-indicators"

def merge_signals_for_ticker_interval(ticker: str, interval: str):
    input_dir = INPUT_BASE / ticker / interval
    if not input_dir.exists():
        logging.warning(f"[!] Missing signal folder: {input_dir}")
        return

    merged_df = None

    for csv_path in sorted(input_dir.glob("*.csv")):
        try:
            # Skip pattern files
            if csv_path.stem in {"doubles", "triangles", "wedges", "head_shoulders"}:
                continue

            df = pd.read_csv(csv_path)

            if df.empty or df.shape[0] < 2:
                raise ValueError("File is empty or too short")

            # Parse time column
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
                df.set_index("Date", inplace=True)
            else:
                df.index = pd.to_datetime(df.iloc[:, 0], errors="coerce", utc=True)
                df.drop(columns=df.columns[0], inplace=True)

            df = df[df.index.notna()]
            if df.empty:
                logging.warning(f"[!] {csv_path.name} has no valid timestamps, skipping")
                continue

            # Smarter prefixing logic to avoid redundancy
            def needs_prefix(stem, col):
                return not col.lower().startswith(stem.lower()) \
                    and not col.lower().startswith(("bb_", "macd", "rsi", "ma_", "obv", "fibonacci"))

            df.columns = [
                col if not needs_prefix(csv_path.stem, col) else f"{csv_path.stem}_{col}"
                for col in df.columns
            ]
            df.index.name = "Date"

            if merged_df is None:
                merged_df = df
            else:
                overlapping = set(df.columns) & set(merged_df.columns)
                if overlapping:
                    df = df.rename(columns={col: f"{col}_{csv_path.stem}" for col in overlapping})
                merged_df = merged_df.join(df, how="outer")

        except Exception as e:
            logging.error(f"[!] Failed to read {csv_path}: {e}")

    # --- Add price columns from cleaned data ---
    try:
        cleaned = load_td([ticker], interval)
        if ticker not in cleaned:
            logging.warning(f"[!] Missing cleaned file: {ticker} ({interval})")
        else:
            price_df = cleaned[ticker]
            price_df = price_df[["Open", "High", "Low", "Close", "Volume"]]
            merged_df = price_df.join(merged_df, how="outer")
    except Exception as e:
        logging.warning(f"[!] Could not join price data for {ticker} {interval}: {e}")

    if merged_df is not None and not merged_df.empty:
        merged_df.sort_index(inplace=True)
        outdir = OUTPUT_BASE / ticker
        outdir.mkdir(parents=True, exist_ok=True)
        outfile = outdir / f"{interval}.csv"
        merged_df.to_csv(outfile)
        logging.info(f"[✓] Merged {ticker} ({interval}) → {outfile}")
    else:
        logging.warning(f"[!] No valid files to merge for {ticker} ({interval})")

def run_merge_indicators():
    tickers = [d.name for d in INPUT_BASE.iterdir() if d.is_dir()]
    for ticker in tickers:
        for interval in os.listdir(INPUT_BASE / ticker):
            merge_signals_for_ticker_interval(ticker, interval)

def main(intervals=None):
    intervals = intervals or ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]
    tickers = [d.name for d in INPUT_BASE.iterdir() if d.is_dir()]
    for ticker in tickers:
        for interval in intervals:
            merge_signals_for_ticker_interval(ticker, interval)

if __name__ == "__main__":
    main()
