# stonkslib/fetch/fetch.py
import os
import logging
import click
import yaml
import pandas as pd
import yfinance as yf
from datetime import datetime

# Setup logging
LOG_DIR = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "log")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "fetch_options.log")),
        logging.StreamHandler()
    ]
)

# Correctly resolve project root (two levels up from this file)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TICKER_YAML = os.path.join(PROJECT_ROOT, "tickers.yaml")

def load_tickers(category=None, yaml_file=TICKER_YAML):
    """Load tickers from the YAML config file."""
    try:
        with open(yaml_file, "r") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        logging.error(f"[!] Failed to load tickers.yaml: {e}")
        return []

    if category:
        return [sym for sym in data.get(category, []) if not sym.endswith('-USD')]
    return [sym for cat in ["stocks", "etfs"] for sym in data.get(cat, []) if not sym.endswith('-USD')]

def fetch_all_options(output_dir, min_days_out, max_days_out, option_type, symbols):
    """Fetch option chains and save to specified output directory."""
    for symbol in symbols:
        try:
            ticker_obj = yf.Ticker(symbol)
            expirations = ticker_obj.options
            if not expirations:
                logging.warning(f"[!] No options data available for {symbol}")
                continue

            df_list = []
            now_utc = pd.Timestamp.now(tz='UTC')

            for exp in expirations:
                try:
                    exp_date = pd.to_datetime(exp, errors='coerce').tz_localize(None).tz_localize('UTC')
                    if exp_date is pd.NaT:
                        logging.warning(f"[!] Invalid expiration date for {symbol}: {exp}")
                        continue

                    days_diff = (exp_date - now_utc).days
                    if min_days_out <= days_diff <= max_days_out:
                        opt = ticker_obj.option_chain(exp)
                        df = opt.calls if option_type == "calls" else opt.puts
                        df = df.copy()
                        df["expirationDate"] = exp_date
                        df["ticker"] = symbol
                        df["daysToExpiration"] = days_diff
                        df_list.append(df)
                except Exception as e:
                    logging.error(f"[!] Failed to fetch option chain for {symbol} exp {exp}: {e}")
                    continue

            if df_list:
                df = pd.concat(df_list, ignore_index=True)
                os.makedirs(output_dir, exist_ok=True)
                outfile = os.path.join(output_dir, f"{symbol}.csv")
                df.to_csv(outfile, index=False)
                logging.info(f"[✓] Saved {option_type} for {symbol} → {outfile} ({len(df)} rows)")
            else:
                logging.info(f"[✗] No {option_type} saved for {symbol}")

        except Exception as e:
            logging.error(f"[!] Failed to fetch options for {symbol}: {e}")

@click.group()
def fetch():
    """Fetch raw data (OHLCV, options, etc)."""

@fetch.command("stocks")
@click.option("--force", is_flag=True, help="Force re-download and overwrite existing CSVs")
def fetch_stocks(force):
    """Fetch stock OHLCV data."""
    fetch_all(force=force, category="stocks")

@fetch.command("etfs")
@click.option("--force", is_flag=True, help="Force re-download and overwrite existing CSVs")
def fetch_etf(force):
    """Fetch ETF OHLCV data."""
    fetch_all(force=force, category="etfs")

@fetch.command("crypto")
@click.option("--force", is_flag=True, help="Force re-download and overwrite existing CSVs")
def fetch_crypto(force):
    """Fetch crypto OHLCV data."""
    fetch_all(force=force, category="crypto")

# ================== OPTIONS COMMANDS ==================
@fetch.group()
def options():
    """Fetch option chains and strategy-specific options."""

@options.group()
def buy():
    """Buy side options."""

@options.group()
def sell():
    """Sell side options."""

# -------- BUY SHORTCUTS ---------
@buy.command("leaps")
@click.option("--option_type", type=click.Choice(["calls", "puts"]), default="calls")
@click.option("--ticker", type=str, default=None)
def buy_leaps(option_type, ticker):
    """Fetch LEAPS for buy-side calls or puts (default: calls)."""
    run_options_fetch("buy", option_type, "leaps", ticker)

@buy.command("weekly")
@click.option("--option_type", type=click.Choice(["calls", "puts"]), default="calls")
@click.option("--ticker", type=str, default=None)
def buy_weekly(option_type, ticker):
    """Fetch weekly expiry for buy-side calls or puts (default: calls)."""
    run_options_fetch("buy", option_type, "weekly", ticker)

@buy.command("monthly")
@click.option("--option_type", type=click.Choice(["calls", "puts"]), default="calls")
@click.option("--ticker", type=str, default=None)
def buy_monthly(option_type, ticker):
    """Fetch monthly expiry for buy-side calls or puts (default: calls)."""
    run_options_fetch("buy", option_type, "monthly", ticker)

@buy.command("custom")
@click.option("--option_type", type=click.Choice(["calls", "puts"]), default="calls")
@click.option("--ticker", type=str, default=None)
def buy_custom(option_type, ticker):
    """Fetch custom expiry for buy-side calls or puts (default: calls)."""
    run_options_fetch("buy", option_type, "custom", ticker)

# -------- SELL SHORTCUTS & STRATEGY COMMANDS ---------
@sell.command("leaps")
@click.option("--option_type", type=click.Choice(["calls", "puts"]), default="calls")
@click.option("--ticker", type=str, default=None)
def sell_leaps(option_type, ticker):
    """Fetch LEAPS for sell-side calls or puts (default: calls)."""
    run_options_fetch("sell", option_type, "leaps", ticker)

@sell.command("weekly")
@click.option("--option_type", type=click.Choice(["calls", "puts"]), default="calls")
@click.option("--ticker", type=str, default=None)
def sell_weekly(option_type, ticker):
    """Fetch weekly expiry for sell-side calls or puts (default: calls)."""
    run_options_fetch("sell", option_type, "weekly", ticker)

@sell.command("monthly")
@click.option("--option_type", type=click.Choice(["calls", "puts"]), default="calls")
@click.option("--ticker", type=str, default=None)
def sell_monthly(option_type, ticker):
    """Fetch monthly expiry for sell-side calls or puts (default: calls)."""
    run_options_fetch("sell", option_type, "monthly", ticker)

@sell.command("custom")
@click.option("--option_type", type=click.Choice(["calls", "puts"]), default="calls")
@click.option("--ticker", type=str, default=None)
def sell_custom(option_type, ticker):
    """Fetch custom expiry for sell-side calls or puts (default: calls)."""
    run_options_fetch("sell", option_type, "custom", ticker)

# ----- Strategy subcommands under SELL -----
@sell.command("covered_calls")
@click.option("--ticker", type=str, default=None)
@click.option("--term", type=click.Choice(["weekly", "monthly", "leaps", "custom"]), default="monthly")
def covered_calls(term, ticker):
    """Fetch option chains for covered call strategy (sell calls)."""
    run_options_fetch("sell", "calls", term, ticker, strategy="covered_calls")

@sell.command("secured_puts")
@click.option("--ticker", type=str, default=None)
@click.option("--term", type=click.Choice(["weekly", "monthly", "leaps", "custom"]), default="monthly")
def secured_puts(term, ticker):
    """Fetch option chains for cash secured put strategy (sell puts)."""
    run_options_fetch("sell", "puts", term, ticker, strategy="secured_puts")

# ---- Core fetch logic -----
def run_options_fetch(side, option_type, term, ticker, strategy=None):
    if term == "leaps":
        min_dte, max_dte = 270, 9999
    elif term == "weekly":
        min_dte, max_dte = 7, 13
    elif term == "monthly":
        min_dte, max_dte = 30, 45
    elif term == "custom":
        min_dte, max_dte = 0, 9999
    else:
        min_dte, max_dte = 21, 45  # Default for strategies

    # Set output directory dynamically
    strategy = strategy or term
    output_dir = os.path.join("data", "options_data", "raw", option_type, side, strategy)

    os.makedirs(output_dir, exist_ok=True)

    def ticker_list():
        if ticker:
            return [ticker]
        return load_tickers()

    # Call the fetch function
    fetch_all_options(
        output_dir=output_dir,
        min_days_out=min_dte,
        max_days_out=max_dte,
        option_type=option_type,
        symbols=ticker_list()
    )
    print(f"[✓] Options data saved to {output_dir}/<TICKER>.csv")

if __name__ == "__main__":
    fetch()
