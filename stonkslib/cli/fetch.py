# stonkslib/cli/fetch.py
import os
import click
import yaml
from pathlib import Path
from stonkslib.fetch.data import fetch_all
from stonkslib.fetch.options.od import fetch_all_options, load_tickers
from stonkslib.utils.logging import setup_logging

# Load configuration
PROJECT_ROOT = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
with open(PROJECT_ROOT / "config.yaml", "r") as f:
    config = yaml.safe_load(f)
TICKER_YAML = PROJECT_ROOT / config["project"]["ticker_yaml"]
OUTPUT_BASE_DIR = PROJECT_ROOT / config["project"]["options_data_dir"]
LOG_DIR = PROJECT_ROOT / config["project"]["log_dir"]

# Setup logging
logger = setup_logging(LOG_DIR, "fetch.log")

__all__ = ["fetch", "options"]

@click.group()
def fetch():
    """Fetch raw data (OHLCV, options, etc)."""

@fetch.command("stocks")
@click.option("--force", is_flag=True, help="Force re-download and overwrite existing CSVs")
def fetch_stocks(force):
    """Fetch stock OHLCV data."""
    logger.info("Fetching stock OHLCV data...")
    fetch_all(yaml_file=TICKER_YAML, data_dir=PROJECT_ROOT / config["project"]["ticker_data_dir"], force=force, category="stocks")

@fetch.command("etfs")
@click.option("--force", is_flag=True, help="Force re-download and overwrite existing CSVs")
def fetch_etf(force):
    """Fetch ETF OHLCV data."""
    logger.info("Fetching ETF OHLCV data...")
    fetch_all(yaml_file=TICKER_YAML, data_dir=PROJECT_ROOT / config["project"]["ticker_data_dir"], force=force, category="etfs")

@fetch.command("crypto")
@click.option("--force", is_flag=True, help="Force re-download and overwrite existing CSVs")
def fetch_crypto(force):
    """Fetch crypto OHLCV data."""
    logger.info("Fetching crypto OHLCV data...")
    fetch_all(yaml_file=TICKER_YAML, data_dir=PROJECT_ROOT / config["project"]["ticker_data_dir"], force=force, category="crypto")

@fetch.group()
def options():
    """Fetch option chains and strategy-specific options."""

@options.group()
def buy():
    """Buy side options."""

@options.group()
def sell():
    """Sell side options."""

@buy.command("leaps")
@click.option("--option_type", type=click.Choice(["calls", "puts"]), default="calls")
@click.option("--ticker", type=str, default=None)
def buy_leaps(option_type, ticker):
    """Fetch LEAPS for buy-side calls or puts (default: calls)."""
    logger.info(f"Fetching buy-side LEAPS for {ticker or 'all tickers'}...")
    run_options_fetch("buy", option_type, "leaps", ticker)

@buy.command("weekly")
@click.option("--option_type", type=click.Choice(["calls", "puts"]), default="calls")
@click.option("--ticker", type=str, default=None)
def buy_weekly(option_type, ticker):
    """Fetch weekly expiry for buy-side calls or puts (default: calls)."""
    logger.info(f"Fetching buy-side weekly options for {ticker or 'all tickers'}...")
    run_options_fetch("buy", option_type, "weekly", ticker)

@buy.command("monthly")
@click.option("--option_type", type=click.Choice(["calls", "puts"]), default="calls")
@click.option("--ticker", type=str, default=None)
def buy_monthly(option_type, ticker):
    """Fetch monthly expiry for buy-side calls or puts (default: calls)."""
    logger.info(f"Fetching buy-side monthly options for {ticker or 'all tickers'}...")
    run_options_fetch("buy", option_type, "monthly", ticker)

@buy.command("custom")
@click.option("--option_type", type=click.Choice(["calls", "puts"]), default="calls")
@click.option("--ticker", type=str, default=None)
def buy_custom(option_type, ticker):
    """Fetch custom expiry for buy-side calls or puts (default: calls)."""
    logger.info(f"Fetching buy-side custom options for {ticker or 'all tickers'}...")
    run_options_fetch("buy", option_type, "custom", ticker)

@sell.command("leaps")
@click.option("--option_type", type=click.Choice(["calls", "puts"]), default="calls")
@click.option("--ticker", type=str, default=None)
def sell_leaps(option_type, ticker):
    """Fetch LEAPS for sell-side calls or puts (default: calls)."""
    logger.info(f"Fetching sell-side LEAPS for {ticker or 'all tickers'}...")
    run_options_fetch("sell", option_type, "leaps", ticker)

@sell.command("weekly")
@click.option("--option_type", type=click.Choice(["calls", "puts"]), default="calls")
@click.option("--ticker", type=str, default=None)
def sell_weekly(option_type, ticker):
    """Fetch weekly expiry for sell-side calls or puts (default: calls)."""
    logger.info(f"Fetching sell-side weekly options for {ticker or 'all tickers'}...")
    run_options_fetch("sell", option_type, "weekly", ticker)

@sell.command("monthly")
@click.option("--option_type", type=click.Choice(["calls", "puts"]), default="calls")
@click.option("--ticker", type=str, default=None)
def sell_monthly(option_type, ticker):
    """Fetch monthly expiry for sell-side calls or puts (default: calls)."""
    logger.info(f"Fetching sell-side monthly options for {ticker or 'all tickers'}...")
    run_options_fetch("sell", option_type, "monthly", ticker)

@sell.command("custom")
@click.option("--option_type", type=click.Choice(["calls", "puts"]), default="calls")
@click.option("--ticker", type=str, default=None)
def sell_custom(option_type, ticker):
    """Fetch custom expiry for sell-side calls or puts (default: calls)."""
    logger.info(f"Fetching sell-side custom options for {ticker or 'all tickers'}...")
    run_options_fetch("sell", option_type, "custom", ticker)

@sell.command("covered_calls")
@click.option("--ticker", type=str, default=None)
@click.option("--term", type=click.Choice(["weekly", "monthly", "leaps", "custom"]), default="monthly")
def covered_calls(term, ticker):
    """Fetch option chains for covered call strategy (sell calls)."""
    logger.info(f"Fetching covered calls for {ticker or 'all tickers'}...")
    run_options_fetch("sell", "calls", term, ticker, strategy="covered_calls")

@sell.command("secured_puts")
@click.option("--ticker", type=str, default=None)
@click.option("--term", type=click.Choice(["weekly", "monthly", "leaps", "custom"]), default="monthly")
def secured_puts(term, ticker):
    """Fetch option chains for cash secured put strategy (sell puts)."""
    logger.info(f"Fetching secured puts for {ticker or 'all tickers'}...")
    run_options_fetch("sell", "puts", term, ticker, strategy="secured_puts")

def run_options_fetch(side, option_type, term, ticker, strategy=None):
    strategy_name = strategy or term
    strat_config = config["strategies"].get(strategy_name, {
        "min_dte": 21,
        "max_dte": 45,
        "option_type": option_type,
        "side": side,
        "output_dir": f"{option_type}/{side}/{strategy_name}"
    })
    output_dir = PROJECT_ROOT / config["project"]["options_data_dir"] / strat_config["output_dir"]
    logger.info(f"Resolved output directory: {output_dir}")
    fetch_all_options(
        output_dir=output_dir,
        min_days_out=strat_config["min_dte"],
        max_days_out=strat_config["max_dte"],
        option_type=strat_config["option_type"],
        symbols=[ticker] if ticker else load_tickers()
    )
    print(f"[✓] Options data saved to {output_dir}/<TICKER>.csv")

if __name__ == "__main__":
    fetch()