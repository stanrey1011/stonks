import os
import yaml
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TICKER_YAML_PATH = os.path.join(BASE_DIR, "tickers.yaml")
DATA_OUTPUT_DIR = os.path.join(BASE_DIR, "..", "data", "ticker_data")
YEARS_BACK = 4

def load_tickers(path=TICKER_YAML_PATH):
    with open(path, "r") as f:
        return yaml.safe_load(f)

def get_existing_dates(ticker_file):
    if os.path.exists(ticker_file):
        df = pd.read_csv(ticker_file)
        if not df.empty and "Date" in df.columns:
            # Parse dates, convert invalid to NaT
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            # Drop rows with invalid dates
            df = df.dropna(subset=["Date"])
            if not df.empty:
                return df["Date"].max()
    return None

def fetch_and_update(ticker, start_date, end_date):
    file_path = os.path.join(DATA_OUTPUT_DIR, f"{ticker}.csv")
    existing_max_date = get_existing_dates(file_path)

    if existing_max_date:
        fetch_start = existing_max_date + timedelta(days=1)
    else:
        fetch_start = start_date

    if fetch_start >= end_date:
        print(f"[↺] {ticker} is already up to date.")
        return  # <-- this return must be inside the function!

    print(f"[↓] Fetching {ticker} from {fetch_start.date()} to {end_date.date()}")

    try:
        df = yf.download(ticker, start=fetch_start.strftime('%Y-%m-%d'), 
                          end=end_date.strftime('%Y-%m-%d'), auto_adjust=True)
        if df.empty:
            print(f"[!] No new data for {ticker}")
            return  # also inside try, inside function

        df.reset_index(inplace=True)
        df["Date"] = pd.to_datetime(df["Date"])

        if os.path.exists(file_path):
            df.to_csv(file_path, mode='a', header=False, index=False)
        else:
            df.to_csv(file_path, index=False)

        print(f"[✔] Updated: {ticker}")

    except Exception as e:
        print(f"[✘] Error fetching {ticker}: {e}")

def main():
    tickers = load_tickers()
    end_date = datetime.today()
    start_date = end_date - timedelta(days=365 * YEARS_BACK)

    for category in tickers:
        for ticker in tickers[category]:
            fetch_and_update(ticker, start_date, end_date)

if __name__ == "__main__":
    os.makedirs(DATA_OUTPUT_DIR, exist_ok=True)
    main()
