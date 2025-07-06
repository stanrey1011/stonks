import os
import click
import yaml
from stonkslib.utils.clean_td import clean_td
from stonkslib.utils.clean_od import clean_options_data

# Resolve project root two levels up from this file
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TICKER_YAML = os.path.join(PROJECT_ROOT, "tickers.yaml")

def load_tickers(yaml_file=TICKER_YAML):
    with open(yaml_file, "r") as f:
        data = yaml.safe_load(f)
    return data.get("stocks", []) + data.get("crypto", []) + data.get("etfs", [])

@click.group()
def clean():
    """Clean raw and options data."""

@clean.command()
@click.option("--force", is_flag=True, help="Force overwrite existing clean files")
def tickers(force):
    """Clean stock, ETF, and crypto OHLC data."""
    tickers = load_tickers()
    intervals = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]
    for ticker in tickers:
        for interval in intervals:
            try:
                df = clean_td(ticker, interval, force=force)
                if df is not None:
                    click.echo(f"[✓] Cleaned {ticker} ({interval}) — {len(df)} rows")
            except Exception as e:
                click.echo(f"[!] Failed to clean {ticker} ({interval}): {e}")

@clean.command()
def options():
    """Clean options data."""
    for opt_type in ["calls", "puts"]:
        for side in ["buy", "sell"]:
            for term in ["leaps", "weekly", "monthly", "custom"]:
                raw_dir = f"data/options_data/raw/{opt_type}/{side}/{term}"
                clean_dir = f"data/options_data/clean/{opt_type}/{side}/{term}"
                if os.path.exists(raw_dir):
                    click.echo(f"[i] Cleaning options in {raw_dir} ...")
                    clean_options_data(raw_dir, clean_dir)
