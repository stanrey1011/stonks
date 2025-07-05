# stonkslib/utils/clean_td.py

from pathlib import Path
import pandas as pd

COLUMNS = ["Open", "High", "Low", "Close", "Volume"]

# Resolve root directory automatically
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_BASE = PROJECT_ROOT / "data" / "ticker_data" / "raw"
CLEAN_BASE = PROJECT_ROOT / "data" / "ticker_data" / "clean"

def clean_td(ticker, interval, force=False, verbose=True):
    raw_path = RAW_BASE / interval / f"{ticker}.csv"
    clean_path = CLEAN_BASE / interval / f"{ticker}.csv"

    if not raw_path.exists():
        if verbose:
            print(f"[!] No raw data for {ticker} ({interval})")
        return None

    try:
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
        if interval in ["1d", "1wk"]:
            df.index = df.index.tz_convert('UTC') if df.index.tz is not None else df.index.tz_localize('UTC')
            df.index = df.index.normalize()
        else:
            df.index = df.index.tz_convert('UTC') if df.index.tz is not None else df.index.tz_localize('UTC')

        if df.empty or df.index[0].year < 1980:
            print(f"[!] Data looks wrong after cleaning {ticker} ({interval})—please check your raw file!")
            return None

        clean_path.parent.mkdir(parents=True, exist_ok=True)
        if force or not clean_path.exists():
            df.to_csv(clean_path)
            if verbose:
                print(f"[✔] Cleaned data written: {clean_path}")

        return df

    except Exception as e:
        print(f"[!] Cleaning failed for {ticker} ({interval}): {e}")
        return None
