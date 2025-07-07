# stonkslib/fetch/options/od.py
import os
import logging
import pandas as pd
import yfinance as yf
import yaml
from datetime import datetime
from pathlib import Path
from stonkslib.utils.logging import setup_logging

# Load configuration
PROJECT_ROOT = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
with open(PROJECT_ROOT / "config.yaml", "r") as f:
    config = yaml.safe_load(f)
TICKER_YAML = PROJECT_ROOT / config["project"]["ticker_yaml"]
OUTPUT_BASE_DIR = PROJECT_ROOT / config["project"]["options_data_dir"]
LOG_DIR = PROJECT_ROOT / config["project"]["log_dir"]

# Setup logging
logger = setup_logging(LOG_DIR, "options.log")

def preprocess_options_data(df):
    """Standardize options data for LLM compatibility."""
    if df.empty:
        return df
    df = df.fillna(0)
    df["expirationDate"] = pd.to_datetime(df["expirationDate"]).dt.strftime("%Y-%m-%d")
    return df

def fetch_option_chain(ticker, min_days_out, max_days_out, option_type):
    """Fetch options chain data."""
    try:
        ticker_obj = yf.Ticker(ticker)
        expirations = ticker_obj.options
        df_list = []
        now_utc = pd.Timestamp.now(tz='UTC')
        for exp in expirations:
            exp_date = pd.to_datetime(exp)
            if exp_date.tzinfo is None:
                exp_date = exp_date.tz_localize('UTC')
            else:
                exp_date = exp_date.tz_convert('UTC')
            dte = (exp_date - now_utc).days
            if min_days_out <= dte <= max_days_out:
                opt = ticker_obj.option_chain(exp)
                contracts = opt.calls.copy() if option_type == "calls" else opt.puts.copy()
                contracts["expirationDate"] = exp_date
                contracts["ticker"] = ticker
                contracts["daysToExpiration"] = dte
                contracts["optionType"] = option_type
                df_list.append(contracts)
        return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()
    except Exception as e:
        logger.error(f"[!] Failed to fetch options for {ticker}: {e}")
        return pd.DataFrame()

def fetch_all_options(output_dir, min_days_out, max_days_out, option_type, symbols=None):
    """Fetch options data for a list of symbols."""
    output_dir = Path(output_dir)
    with open(TICKER_YAML, "r") as f:
        tickers = yaml.safe_load(f)
    if symbols is None:
        categories = ["stocks", "etfs"]
        all_symbols = [sym for cat in categories for sym in tickers.get(cat, [])]
    else:
        all_symbols = symbols
    output_dir.mkdir(parents=True, exist_ok=True)
    for symbol in all_symbols:
        df = fetch_option_chain(symbol, min_days_out, max_days_out, option_type)
        if not df.empty:
            df = preprocess_options_data(df)
            outfile = output_dir / f"{symbol}.csv"
            df.to_csv(outfile, index=False)
            logger.info(f"[✓] Saved {option_type} for {symbol} → {outfile} ({len(df)} rows)")
        else:
            logger.info(f"[✗] No {option_type} saved for {symbol}")

def load_tickers(category=None, yaml_file=TICKER_YAML):
    """Load tickers from YAML."""
    try:
        with open(yaml_file, "r") as f:
            data = yaml.safe_load(f) or {}
        if not data.get("stocks") and not data.get("etfs"):
            logger.error(f"[!] No stocks or ETFs found in {yaml_file}")
            return []
        if category:
            return [sym for sym in data.get(category, []) if not sym.endswith('-USD')]
        return [sym for cat in ["stocks", "etfs"] for sym in data.get(cat, []) if not sym.endswith('-USD')]
    except Exception as e:
        logger.error(f"[!] Failed to load {yaml_file}: {e}")
        return []

if __name__ == "__main__":
    for strategy, params in config["strategies"].items():
        fetch_all_options(
            output_dir=PROJECT_ROOT / config["project"]["options_data_dir"] / params["output_dir"],
            min_days_out=params["min_dte"],
            max_days_out=params["max_dte"],
            option_type=params["option_type"],
            symbols=["AAPL", "MSFT", "NVDA"]
        )