import os
import logging
import pandas as pd
import yfinance as yf
import yaml

# --- Config ---
MIN_DTE = 7
MAX_DTE = 45
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../.."))
TICKER_YAML = os.path.join(PROJECT_ROOT, "tickers.yaml")

ANALYSIS_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "analysis", "options", "calls", "sell")

# --- Logging ---
LOG_DIR = os.path.join(PROJECT_ROOT, "log")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "fetch_covered_calls.log")),
        logging.StreamHandler()
    ]
)

def fetch_option_chain(ticker, min_days_out=MIN_DTE, max_days_out=MAX_DTE):
    try:
        ticker_obj = yf.Ticker(ticker)
        expirations = ticker_obj.options
        if not expirations:
            logging.warning(f"[!] No options data available for {ticker}")
            return pd.DataFrame()

        df_list = []
        now_utc = pd.Timestamp.now(tz='UTC')

        for exp in expirations:
            try:
                exp_date = pd.to_datetime(exp, errors='coerce').tz_localize(None).tz_localize('UTC')
                if pd.isna(exp_date):
                    logging.warning(f"[!] Invalid expiration date for {ticker}: {exp}")
                    continue

                days_diff = (exp_date - now_utc).days
                logging.debug(f"[DEBUG] {ticker} expiration: {exp_date}, days to expiration: {days_diff}")

                if min_days_out <= days_diff <= max_days_out:
                    opt = ticker_obj.option_chain(exp)
                    calls_df = opt.calls.copy()
                    calls_df["expirationDate"] = exp_date
                    calls_df["ticker"] = ticker
                    calls_df["daysToExpiration"] = days_diff
                    df_list.append(calls_df)
            except Exception as e:
                logging.error(f"[!] Failed to fetch option chain for {ticker} exp {exp}: {e}")
                continue

        return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()

    except Exception as e:
        logging.error(f"[!] Failed to fetch options for {ticker}: {e}")
        return pd.DataFrame()

def fetch_all_covered_calls():
    try:
        with open(TICKER_YAML, "r") as f:
            tickers = yaml.safe_load(f) or {}
    except Exception as e:
        logging.error(f"[!] Failed to load tickers.yaml: {e}")
        return

    categories = ["stocks", "etfs"]
    all_symbols = [sym for cat in categories for sym in tickers.get(cat, []) if not sym.endswith('-USD')]

    if not all_symbols:
        logging.error("[!] No valid symbols found in tickers.yaml")
        return

    for symbol in all_symbols:
        df = fetch_option_chain(symbol)
        if not df.empty:
            outdir = os.path.join(ANALYSIS_OUTPUT_DIR, symbol)
            os.makedirs(outdir, exist_ok=True)
            outfile = os.path.join(outdir, "covered_calls.csv")
            df.to_csv(outfile, index=False)
            logging.info(f"[✓] Saved covered calls for {symbol} → {outfile} ({len(df)} rows)")
        else:
            logging.info(f"[✗] No covered calls saved for {symbol}")

# --- CLI Safe Entrypoint ---
if __name__ == "__main__":
    fetch_all_covered_calls()
