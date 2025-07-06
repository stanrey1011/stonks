import os
import sys
import yaml
import pandas as pd
import yfinance as yf
from pathlib import Path
import warnings

from stonkslib.fetch.guard import needs_update
from stonkslib.fetch.ranges import CATEGORY_INTERVALS

# Suppress warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")


def fetch_all(yaml_file="tickers.yaml", data_dir="data", force=False, tickers=None, category=None):
    base_dir = Path.cwd() if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]
    yaml_path = base_dir / yaml_file
    raw_data_path = base_dir / data_dir / "ticker_data" / "raw"

    with open(yaml_path, "r") as f:
        all_tickers = yaml.safe_load(f)

    # Debugging: Print categories available
    print(f"Available categories in YAML: {all_tickers.keys()}")

    # If a list of tickers is explicitly given, fetch only those, using "stocks" intervals by default
    if tickers is not None:
        target_tickers = tickers
        # Guess the category, fallback to stocks
        intervals = CATEGORY_INTERVALS.get(category or "stocks", [("1d", "1y")])
        cats = [category or "stocks"]
    elif category:
        # If category is provided, fetch only that category
        cats = [category]
    else:
        # If no category is provided, fetch from all categories
        cats = all_tickers.keys()

    # Debugging: Print tickers being loaded
    for cat in cats:
        print(f"Loading {cat} category...")
        if tickers is not None:
            these_tickers = target_tickers
        else:
            these_tickers = all_tickers.get(cat, [])

        print(f"Loading {cat} tickers: {these_tickers}")  # Debugging line
        intervals = CATEGORY_INTERVALS.get(cat, [("1d", "1y")])

        for ticker in these_tickers:
            for interval, period in intervals:
                interval_str = str(interval)
                csv_path = raw_data_path / interval_str / f"{ticker}.csv"

                if not force and not needs_update(csv_path, interval_str):
                    if csv_path.exists():
                        try:
                            existing = pd.read_csv(csv_path, index_col=0)
                            existing.index.name = "Date"
                            existing.index = pd.to_datetime(existing.index, utc=True, errors="coerce")
                            existing = existing[existing.index.notna()]
                            latest = existing.index[-1] if not existing.empty else "n/a"
                            print(f"[⏭] Skipping {ticker} ({interval_str}) – {len(existing)} rows, latest: {latest}")
                        except Exception as e:
                            print(f"[⏭] Skipping {ticker} ({interval_str}) – error reading existing data: {e}")
                    else:
                        print(f"[⏭] Skipping {ticker} ({interval_str}) – file not found but considered fresh")
                    continue

                print(f"[↑] Fetching {ticker} ({interval_str}, {period})...")
                try:
                    yf_interval = {"1h": "60m"}.get(interval_str, interval_str)
                    df = yf.download(ticker, interval=interval_str, period=period, progress=False)
                    if not df.empty:
                        df.index.name = "Date"
                        df.index = pd.to_datetime(df.index, utc=True)
                        csv_path.parent.mkdir(parents=True, exist_ok=True)

                        if force or not csv_path.exists():
                            df.to_csv(csv_path)
                            print(f"[✓] Saved {ticker} → {interval_str} (new file, {len(df)} rows, latest: {df.index[-1]})")
                        else:
                            existing = pd.read_csv(csv_path, index_col=0)
                            existing.index.name = "Date"
                            existing.index = pd.to_datetime(existing.index, utc=True, errors="coerce")
                            existing = existing[existing.index.notna()]
                            new_rows = df[~df.index.isin(existing.index)]

                            if new_rows.empty:
                                print(f"[⏭] Skipping {ticker} ({interval_str}) – already up-to-date")
                                continue

                            df = pd.concat([existing, new_rows])
                            df.sort_index(inplace=True)
                            df.to_csv(csv_path)
                            print(f"[✓] Appended {len(new_rows)} rows to {ticker} → {interval_str}, latest: {df.index[-1]})")
                    else:
                        print(f"[!] No data for {ticker} ({interval_str})")
                except Exception as e:
                    print(f"[!] Error fetching {ticker} ({interval_str}): {e}")

if __name__ == "__main__":
    fetch_all()
