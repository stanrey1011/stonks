# stonkslib/merge/by_patterns.py

import os
import pandas as pd
from pathlib import Path
import logging

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_BASE = PROJECT_ROOT / "data" / "analysis" / "signals"
OUTPUT_BASE = PROJECT_ROOT / "data" / "analysis" / "merged" / "by-patterns"
PATTERN_FILES = ["doubles.csv", "triangles.csv", "wedges.csv", "head_shoulders.csv"]

def merge_patterns_for_ticker_interval(ticker: str, interval: str):
    input_dir = INPUT_BASE / ticker / interval
    if not input_dir.exists():
        logging.warning(f"[!] Missing pattern folder: {input_dir}")
        return

    merged_df = pd.DataFrame()

    for filename in PATTERN_FILES:
        csv_path = input_dir / filename
        if not csv_path.exists():
            continue

        try:
            df = pd.read_csv(csv_path)
            if df.empty or df.shape[0] < 1:
                continue

            # Use SECOND column (usually 'start' or 'left') as datetime index for patterns
            date_col = df.columns[1]  # index 1, not 0
            df.rename(columns={date_col: "Date"}, inplace=True)
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
            df = df[df["Date"].notna()]  # Filter out invalid timestamps
            if df.empty:
                continue

            df.set_index("Date", inplace=True)

            # Prefix all columns except the index
            # (Don't prefix the index; only prefix value columns)
            prefixed_cols = [f"{filename.replace('.csv','')}_{col}" for col in df.columns]
            df.columns = prefixed_cols

            merged_df = pd.concat([merged_df, df], axis=0)

        except Exception as e:
            logging.error(f"[!] Failed to read {csv_path}: {e}")

    if not merged_df.empty:
        merged_df.sort_index(inplace=True)

        outdir = OUTPUT_BASE / ticker
        outdir.mkdir(parents=True, exist_ok=True)
        outfile = outdir / f"{interval}.csv"
        merged_df.to_csv(outfile)
        logging.info(f"[+] Merged {ticker} ({interval}) patterns → {outfile}")
    else:
        logging.warning(f"[!] No valid pattern data to merge for {ticker} ({interval})")

def run_merge_patterns():
    tickers = [d.name for d in INPUT_BASE.iterdir() if d.is_dir()]
    for ticker in tickers:
        for interval_path in (INPUT_BASE / ticker).iterdir():
            if interval_path.is_dir():
                merge_patterns_for_ticker_interval(ticker, interval_path.name)

if __name__ == "__main__":
    run_merge_patterns()
