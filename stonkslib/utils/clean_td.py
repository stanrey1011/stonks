# stonkslib/utils/clean_td.py

import os
import pandas as pd

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

COLUMNS = ["Open", "High", "Low", "Close", "Volume"]

def clean_td(ticker, interval, base_dir=BASE_DIR, force=False, verbose=True):
    raw_path = os.path.join(base_dir, "data", "ticker_data", "raw", interval, f"{ticker}.csv")
    clean_path = os.path.join(base_dir, "data", "ticker_data", "clean", interval, f"{ticker}.csv")

    if not os.path.exists(raw_path):
        if verbose:
            print(f"[!] No raw data for {ticker} ({interval})")
        return None

    try:
        # Load, only keep rows that start with a date (YYYY-MM-DD)
        df = pd.read_csv(raw_path, dtype=str)
        df = df[df[df.columns[0]].str.match(r"\d{4}-\d{2}-\d{2}")]

        # Parse date column as UTC, drop unparseable
        df[df.columns[0]] = pd.to_datetime(df[df.columns[0]], errors='coerce', utc=True)
        df.dropna(subset=[df.columns[0]], inplace=True)
        df.rename(columns={df.columns[0]: "Date"}, inplace=True)
        df.set_index("Date", inplace=True)

        # Convert columns to float and drop non-numeric rows
        df = df[COLUMNS].apply(pd.to_numeric, errors="coerce")
        df.dropna(subset=COLUMNS, inplace=True)

        # Robust timezone handling
        # --- For daily and weekly: force to midnight UTC (no time drift)
        if interval in ["1d", "1wk"]:
            # Make sure index is normalized to midnight UTC, and tz-aware
            df.index = df.index.tz_convert('UTC') if df.index.tz is not None else df.index.tz_localize('UTC')
            df.index = df.index.normalize()  # sets time to 00:00:00
        else:
            # For intraday: just make sure tz-aware UTC
            df.index = df.index.tz_convert('UTC') if df.index.tz is not None else df.index.tz_localize('UTC')

        # Final sanity check
        if df.empty or df.index[0].year < 1980:
            print(f"[!] Data looks wrong after cleaning {ticker} ({interval})—please check your raw file!")
            return None

        os.makedirs(os.path.dirname(clean_path), exist_ok=True)
        if force or not os.path.exists(clean_path):
            # Save with timestamp as string (always ISO8601 with UTC)
            df.to_csv(clean_path)
            if verbose:
                print(f"[✔] Cleaned data written: {clean_path}")

        return df

    except Exception as e:
        print(f"[!] Cleaning failed for {ticker} ({interval}): {e}")
        return None
