# fetch_data.py

import os
import yaml
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# === Configuration ===
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # one level up to ~/stonks
TICKER_YAML_PATH = os.path.join(BASE_DIR, "tickers.yaml")
DATA_OUTPUT_DIR = os.path.join(BASE_DIR, "project", "data", "ticker_data")
YEARS_BACK = 4

# === Utilities ===
def load_tickers(yaml_path=TICKER_YAML_PATH):
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {"tickers": data}

def get_last_date_in_file(file_path):
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path, usecols=["Date"])
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"])
            if not df.empty:
                return df["Date"].max()
        except Exception as e:
            print(f"[!] Error reading {file_path}: {e}")
    return None

# === Fetch Logic ===
def fetch_and_update(ticker, start_date, end_date):
    file_path = os.path.join(DATA_OUTPUT_DIR, f"{ticker}.csv")
    last_date = get_last_date_in_file(file_path)
    fetch_start = last_date + timedelta(days=1) if last_date else start_date

    if fetch_start >= end_date:
        print(f"[↺] {ticker} is already up to date.")
        return

    print(f"[↓] Fetching {ticker} from {fetch_start.date()} to {end_date.date()}")

    try:
        df = yf.download(ticker, start=fetch_start.strftime('%Y-%m-%d'),
                         end=end_date.strftime('%Y-%m-%d'), auto_adjust=True)

        if df.empty:
            print(f"[!] No new data for {ticker}")
            return

        df.reset_index(inplace=True)
        df["Date"] = pd.to_datetime(df["Date"])

        if os.path.exists(file_path):
            df.to_csv(file_path, mode='a', header=False, index=False)
        else:
            df.to_csv(file_path, index=False)

        print(f"[✔] Updated: {ticker}")

    except Exception as e:
        print(f"[✘] Failed to fetch {ticker}: {e}")

# === Main Routine ===
def main():
    os.makedirs(DATA_OUTPUT_DIR, exist_ok=True)

    tickers = load_tickers()
    end_date = datetime.today()
    start_date = end_date - timedelta(days=YEARS_BACK * 365)

    for group in tickers.values():
        for ticker in group:
            fetch_and_update(ticker, start_date, end_date)

if __name__ == "__main__":
    main()
