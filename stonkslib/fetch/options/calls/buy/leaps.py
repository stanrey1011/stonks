# stonkslib/fetch/options/buy/calls/leaps.py

import os
import logging
import pandas as pd
import yfinance as yf
import yaml
from datetime import datetime

# --- Config ---
MIN_DTE = 270
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../.."))
TICKER_YAML = os.path.join(PROJECT_ROOT, "tickers.yaml")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "options_data", "raw", "calls", "buy", "leaps")

# --- Logging ---
LOG_DIR = os.path.join(PROJECT_ROOT, "log")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "fetch_leaps.log")),
        logging.StreamHandler()
    ]
)

# --- Fetching ---
def fetch_option_chain(ticker, min_days_out=MIN_DTE):
    try:
        ticker_obj = yf.Ticker(ticker)
        expirations = ticker_obj.options
        df_list = []

        now_utc = pd.Timestamp.now(tz='UTC')  # Simplified: Get current UTC time

        for exp in expirations:
            # Convert expiration to UTC timestamp
            exp_date = pd.to_datetime(exp).tz_localize(None).tz_localize('UTC')
            days_to_exp = (exp_date - now_utc).days

            if days_to_exp >= min_days_out:
                opt = ticker_obj.option_chain(exp)
                calls_df = opt.calls.copy()
                calls_df["expirationDate"] = exp_date
                calls_df["ticker"] = ticker
                calls_df["daysToExpiration"] = days_to_exp  # Add for debugging
                df_list.append(calls_df)

        return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()

    except Exception as e:
        logging.error(f"[!] Failed to fetch options for {ticker}: {e}")
        return pd.DataFrame()

def fetch_all_leaps():
    try:
        with open(TICKER_YAML, "r") as f:
            tickers = yaml.safe_load(f) or {}
    except Exception as e:
        logging.error(f"[!] Failed to load tickers.yaml: {e}")
        return

    # Only pull from stocks and etfs — skip crypto
    categories = ["stocks", "etfs"]
    all_symbols = [sym for cat in categories for sym in tickers.get(cat, [])]

    if not all_symbols:
        logging.error("[!] No symbols found in tickers.yaml")
        return

    for symbol in all_symbols:
        df = fetch_option_chain(symbol)
        if not df.empty:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            outfile = os.path.join(OUTPUT_DIR, f"{symbol}.csv")
            df.to_csv(outfile, index=False) 
            logging.info(f"[✓] Saved LEAPS for {symbol} → {outfile} ({len(df)} rows)")
        else:
            logging.info(f"[✗] No LEAPS saved for {symbol}")

# --- CLI Safe Entrypoint ---
if __name__ == "__main__":
    fetch_all_leaps()