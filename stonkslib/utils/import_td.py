import os
import pandas as pd
import yfinance as yf
import yaml
import warnings
from datetime import datetime

# Suppress specific date format warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")
warnings.filterwarnings("ignore", category=FutureWarning, message="YF.download.*")

# Base directories
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TICKERS_YAML = os.path.join(BASE_DIR, "tickers.yaml")
DATA_DIR = os.path.join(BASE_DIR, "data", "ticker_data", "clean")

def load_tickers():
    with open(TICKERS_YAML) as f:
        data = yaml.safe_load(f)
    return {k: v for k, v in data.items()}

def load_existing_csv(csv_file):
    try:
        return pd.read_csv(csv_file, index_col=0, parse_dates=True)
    except Exception as e:
        print(f"[error] failed to load {csv_file}: {e}")
        return None

def get_last_timestamp(df):
    if df is not None and not df.empty:
        return df.index[-1]
    return None

def fetch_data(ticker, interval, start_date=None):
    return yf.download(ticker, interval=interval, start=start_date, progress=False)

def import_all():
    tickers_by_group = load_tickers()

    for group, tickers in tickers_by_group.items():
        for ticker in tickers:
            for interval in ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]:
                subdir = os.path.join(DATA_DIR, interval)
                os.makedirs(subdir, exist_ok=True)

                csv_file = os.path.join(subdir, f"{ticker}.csv")
                existing_df = load_existing_csv(csv_file)

                if existing_df is not None:
                    try:
                        last_ts = get_last_timestamp(existing_df)
                        print(f"[debug] Last clean timestamp for {ticker} ({interval}): {last_ts}")
                        new_df = fetch_data(ticker, interval=interval, start_date=last_ts)
                        if new_df is not None and not new_df.empty:
                            new_df = new_df[~new_df.index.isin(existing_df.index)]
                            if not new_df.empty:
                                updated_df = pd.concat([existing_df, new_df])
                                updated_df.to_csv(csv_file)
                                print(f"[{interval}] {ticker} – appended {len(new_df)} rows")
                            else:
                                print(f"[{interval}] {ticker} – up to date, no new rows")
                        else:
                            print(f"[{interval}] {ticker} – no new data")
                    except Exception as e:
                        print(f"[{interval}] {ticker} – error updating: {e}")
                else:
                    try:
                        df = fetch_data(ticker, interval=interval)
                        if df is not None and not df.empty:
                            df.to_csv(csv_file)
                            print(f"[{interval}] {ticker} – created with {len(df)} rows")
                        else:
                            print(f"[{interval}] {ticker} – no data to create")
                    except Exception as e:
                        print(f"[{interval}] {ticker} – error creating: {e}")

if __name__ == "__main__":
    import_all()
