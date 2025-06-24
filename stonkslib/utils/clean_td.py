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
        # Try loading with possible extra rows skipped
        df = pd.read_csv(raw_path, dtype=str)
        # Remove rows where the first column is not a date
        df = df[df[df.columns[0]].str.match(r"\d{4}-\d{2}-\d{2}")]

        # Parse the date column, drop unparseable
        df[df.columns[0]] = pd.to_datetime(df[df.columns[0]], errors='coerce', utc=True)
        df.dropna(subset=[df.columns[0]], inplace=True)
        df.rename(columns={df.columns[0]: "Date"}, inplace=True)
        df.set_index("Date", inplace=True)

        # Now keep only real numeric columns (float conversion or drop non-numeric)
        COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
        df = df[COLUMNS].apply(pd.to_numeric, errors="coerce")

        # Drop rows with any NaN in price columns
        df.dropna(subset=COLUMNS, inplace=True)

        # Final sanity check
        if df.empty or df.index[0].year < 1980:
            print(f"[!] Data looks wrong after cleaning {ticker} ({interval})—please check your raw file!")
            return None

        os.makedirs(os.path.dirname(clean_path), exist_ok=True)
        if force or not os.path.exists(clean_path):
            df.to_csv(clean_path)
            if verbose:
                print(f"[✔] Cleaned data written: {clean_path}")

        return df

    except Exception as e:
        print(f"[!] Cleaning failed for {ticker} ({interval}): {e}")
        return None
