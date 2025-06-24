# stonkslib/stonks_cli.py

import os
import click
import yaml
import warnings

from stonkslib.fetch.data import fetch_all
from stonkslib.utils.clean_td import clean_td
from stonkslib.utils.load_td import load_td
from stonkslib.utils.wipe_raw_td import clear_raw_td
from stonkslib.utils.wipe_clean_td import clear_clean_td

# Suppress specific pandas date warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TICKER_YAML = os.path.join(BASE_DIR, "tickers.yaml")

def load_tickers(yaml_file=TICKER_YAML):
    with open(yaml_file, "r") as f:
        data = yaml.safe_load(f)
    return data.get("stocks", []) + data.get("crypto", []) + data.get("etfs", [])

@click.group()
def cli():
    """Stonks CLI"""
    pass

@cli.command(name="fetch")
@click.option("--force", is_flag=True, help="Force re-download and overwrite existing CSVs")
def fetch_cmd(force):
    """Fetch all data for all tickers with predefined intervals"""
    fetch_all(force=force)

@cli.command(name="clean")
@click.option("--force", is_flag=True, help="Force overwrite existing clean files")
def clean_cmd(force):
    """Clean and standardize raw CSVs into clean directory"""
    tickers = load_tickers()
    intervals = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]

    for ticker in tickers:
        for interval in intervals:
            try:
                df = clean_td(ticker, interval, force=force)
                if df is not None:
                    print(f"[✓] Cleaned {ticker} ({interval}) — {len(df)} rows")
            except Exception as e:
                print(f"[!] Failed to clean {ticker} ({interval}): {e}")

@cli.command(name="wipe")
@click.option("--target", type=click.Choice(["raw", "clean", "all"]), default="raw", help="Target directory to wipe")
def wipe_cmd(target):
    """Wipe raw or clean ticker data folders"""
    if target == "raw":
        clear_raw_td()
    elif target == "clean":
        clear_clean_td()
    elif target == "all":
        clear_raw_td()
        clear_clean_td()
