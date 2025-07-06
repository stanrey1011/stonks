import os
import logging
import pandas as pd
import yfinance as yf
import yaml
from datetime import datetime

# --- Config ---
MIN_DTE = 270
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
TICKER_YAML = os.path.join(PROJECT_ROOT, "tickers.yaml")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "options_data", "raw", "calls", "buy", "leaps")

# --- Logging ---
LOG_DIR = os.path.join(PROJECT_ROOT, "log")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "fetch_options.log")),
        logging.StreamHandler()
    ]
)

def fetch_option_chain(
    ticker,
    min_days_out=0,
    max_days_out=9999,
    option_type="calls"  # "calls", "puts", or "both"
):
    try:
        ticker_obj = yf.Ticker(ticker)
        expirations = ticker_obj.options
        df_list = []

        now_utc = pd.Timestamp.now(tz='UTC')
        for exp in expirations:
            exp_date = pd.to_datetime(exp)
            # Make expiration date always UTC-aware
            if exp_date.tzinfo is None:
                exp_date = exp_date.tz_localize('UTC')
            else:
                exp_date = exp_date.tz_convert('UTC')
            dte = (exp_date - now_utc).days
            if min_days_out <= dte <= max_days_out:
                opt = ticker_obj.option_chain(exp)
                if option_type == "calls":
                    contracts = opt.calls.copy()
                elif option_type == "puts":
                    contracts = opt.puts.copy()
                else:  # both
                    contracts = pd.concat([opt.calls, opt.puts], ignore_index=True)
                contracts["expirationDate"] = exp_date
                contracts["ticker"] = ticker
                contracts["daysToExpiration"] = dte
                contracts["optionType"] = option_type if option_type in ["calls", "puts"] else "both"
                df_list.append(contracts)

        return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()
    except Exception as e:
        logging.error(f"[!] Failed to fetch options for {ticker}: {e}")
        return pd.DataFrame()

def fetch_all_options(
    output_dir,
    min_days_out=0,
    max_days_out=9999,
    option_type="calls",
    symbols=None  # Added symbols argument
):
    with open(TICKER_YAML, "r") as f:
        tickers = yaml.safe_load(f)

    if symbols is None:
        # If no symbols passed, fetch from all categories
        categories = ["stocks", "etfs"]
        all_symbols = [sym for cat in categories for sym in tickers.get(cat, [])]
    else:
        all_symbols = symbols  # Use passed symbols if provided

    os.makedirs(output_dir, exist_ok=True)

    for symbol in all_symbols:
        df = fetch_option_chain(symbol, min_days_out, max_days_out, option_type)
        if not df.empty:
            outfile = os.path.join(output_dir, f"{symbol}.csv")
            df.to_csv(outfile, index=False)
            logging.info(f"[✓] Saved {option_type} for {symbol} → {outfile} ({len(df)} rows)")
        else:
            logging.info(f"[✗] No {option_type} saved for {symbol}")

# --- CLI Entrypoint Example ---
if __name__ == "__main__":
    fetch_all_options(
        output_dir="data/options_data/raw/calls/buy/leaps",
        min_days_out=270,
        max_days_out=9999,
        option_type="calls",
        symbols=["AAPL", "MSFT", "NVDA"]  # Example: Pass symbols directly for testing
    )

    # --- Uncomment below to fetch weeklies, monthlies, or puts as needed ---
    # fetch_all_options(
    #     output_dir="data/options_data/raw/puts/buy/weekly",
    #     min_days_out=7,
    #     max_days_out=13,
    #     option_type="puts"
    # )
