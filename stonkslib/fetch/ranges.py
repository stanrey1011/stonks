# stonkslib/fetch/ranges.py

import os
import sys
import yaml
import pandas as pd
import yfinance as yf
from pathlib import Path
from stonkslib.fetch.guard import needs_update
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)

CATEGORY_INTERVALS = {
    "stocks": [
        ("1m", "7d"),
        ("2m", "60d"),
        ("5m", "60d"),
        ("15m", "60d"),
        ("30m", "60d"),
        ("1h", "2y"),
        ("1d", "3y"),
        ("1wk", "4y"),
        ("1mo", "5y"),
    ],
    "etfs": [
        ("1m", "7d"),
        ("2m", "60d"),
        ("5m", "60d"),
        ("15m", "60d"),
        ("30m", "60d"),
        ("1h", "2y"),
        ("1d", "3y"),
        ("1wk", "4y"),
        ("1mo", "5y"),
    ],
    "crypto": [
        ("1m", "7d"),
        ("5m", "60d"),
        ("15m", "60d"),
        ("1d", "2y"),
        ("1wk", "3y"),
    ],
}

def fetch_all(yaml_file="tickers.yaml", data_dir="data", force=False):
    base_dir = Path.cwd() if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]
    yaml_path = base_dir / yaml_file
    data_path = base_dir / data_dir / "ticker_data"

    with open(yaml_path, "r") as f:
        all_tickers = yaml.safe_load(f)

    for category, tickers in all_tickers.items():
        intervals = CATEGORY_INTERVALS.get(category, [("1d", "1y")])

        for ticker in tickers:
            for interval, period in intervals:
                interval_str = "".join(interval) if isinstance(interval, tuple) else interval
                csv_path = data_path / interval_str / f"{ticker}.csv"

                if not force and not needs_update(csv_path, interval_str):
                    if csv_path.exists():
                        try:
                            existing = pd.read_csv(csv_path, index_col=0)
                            existing.index.name = "Date"
                            existing.index = pd.to_datetime(
                                existing.index,
                                format="%Y-%m-%d %H:%M:%S%z",
                                errors="coerce",
                                utc=True,
                            )
                            existing = existing[existing.index.notna()]
                            latest = existing.index[-1] if not existing.empty else "n/a"
                            print(f"[⏭] Skipping {ticker} ({interval_str}) – {len(existing)} rows, latest: {latest}")
                        except Exception as e:
                            print(f"[⏭] Skipping {ticker} ({interval_str}) – error reading existing data: {e}")
                    else:
                        print(f"[⏭] Skipping {ticker} ({interval_str}) – file not found")
                    continue

                print(f"[↑] Fetching {ticker} ({interval_str}, {period})...")
                try:
                    df = yf.download(ticker, interval=interval_str, period=period, progress=False)
                    if not df.empty:
                        df.index = pd.to_datetime(df.index, utc=True)
                        csv_path.parent.mkdir(parents=True, exist_ok=True)

                        if force or not csv_path.exists():
                            df.to_csv(csv_path)
                            print(f"[✓] Saved {ticker} → {interval_str} (new file, {len(df)} rows, latest: {df.index[-1]})")
                        else:
                            existing = pd.read_csv(csv_path, index_col=0)
                            existing.index.name = "Date"
                            existing.index = pd.to_datetime(
                                existing.index,
                                format="%Y-%m-%d %H:%M:%S%z",
                                errors="coerce",
                                utc=True,
                            )
                            existing = existing[existing.index.notna()]
                            new_rows = df[~df.index.isin(existing.index)]

                            if new_rows.empty:
                                print(f"[⏭] Skipping {ticker} ({interval_str}) – already up-to-date")
                                continue

                            df = pd.concat([existing, new_rows])
                            df.sort_index(inplace=True)
                            df.to_csv(csv_path)
                            print(f"[✓] Appended {len(new_rows)} rows to {ticker} → {interval_str}, latest: {df.index[-1]}")
                    else:
                        print(f"[!] No data for {ticker} ({interval_str})")
                except Exception as e:
                    print(f"[!] Error fetching {ticker} ({interval_str}): {e}")
