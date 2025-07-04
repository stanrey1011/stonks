import os
import click
import yaml
import warnings

from stonkslib.fetch.data import fetch_all
from stonkslib.utils.clean_td import clean_td
from stonkslib.utils.load_td import load_td
from stonkslib.utils.wipe_raw_td import clear_raw_td
from stonkslib.utils.wipe_clean_td import clear_clean_td
from stonkslib.utils.wipe_signals import wipe_signals
from stonkslib.analysis.signals import run_signals
from stonkslib.merge.by_indicators import run_merge_indicators
from stonkslib.merge.by_patterns import run_merge_patterns

# === New: strategy config loader ===
from stonkslib.utils.load_strategy import load_strategy_config

# === Backtest imports ===
from stonkslib.backtest.indicators import run_all_backtests as backtest_indicators
try:
    from stonkslib.backtest.doubles import run_all_backtests as backtest_doubles
except ImportError:
    backtest_doubles = None
try:
    from stonkslib.backtest.triangles import run_all_backtests as backtest_triangles
except ImportError:
    backtest_triangles = None
try:
    from stonkslib.backtest.head_shoulders import run_all_backtests as backtest_head_shoulders
except ImportError:
    backtest_head_shoulders = None
try:
    from stonkslib.backtest.wedges import run_all_backtests as backtest_wedges
except ImportError:
    backtest_wedges = None

warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TICKER_YAML = os.path.join(BASE_DIR, "tickers.yaml")
STRATEGY_DIR = os.path.join(os.path.dirname(__file__), "strategies")

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
                    print(f"[\u2713] Cleaned {ticker} ({interval}) — {len(df)} rows")
            except Exception as e:
                print(f"[!] Failed to clean {ticker} ({interval}): {e}")

@cli.command(name="wipe")
@click.option("--target", type=click.Choice(["raw", "clean", "signals", "merged", "all"]), default="raw", help="Target directory to wipe")
def wipe_cmd(target):
    """Wipe raw, clean, signals, merged, or all data folders"""
    class DummyArgs:
        def __init__(self, target):
            self.target = target
    wipe_signals(DummyArgs(target))

@cli.command(name="analyze")
def analyze_cmd():
    """Run signal analysis for all tickers and intervals"""
    run_signals()

@cli.command(name="merge")
@click.option(
    "--target",
    type=click.Choice(["indicators", "patterns", "all"]),
    default="all",
    help="Which data to merge: indicators, patterns, or all",
)
def merge_cmd(target):
    """Merge signals into combined time series format"""
    if target in ("indicators", "all"):
        run_merge_indicators()
    if target in ("patterns", "all"):
        run_merge_patterns()

@cli.command(name="backtest")
@click.option(
    "--target",
    type=click.Choice(["all", "indicators", "doubles", "triangles", "head_shoulders", "wedges"]),
    default="all",
    help="Which backtests to run: indicators, doubles, triangles, head_shoulders, wedges, or all",
)
@click.option(
    "--config",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to strategy YAML config file (default: None for hardcoded backtest logic)",
)
def backtest_cmd(target, config):
    """Run backtests on merged data, using a strategy config if provided"""
    strategy = None
    if config:
        print(f"[*] Loading strategy config: {config}")
        strategy = load_strategy_config(config)

    ran = False
    if target in ("all", "indicators"):
        print("[*] Running indicator backtest...")
        # Pass strategy to your updated backtest (update indicators.py to accept/use strategy!)
        backtest_indicators(strategy)
        ran = True
    if target in ("all", "doubles") and backtest_doubles:
        print("[*] Running doubles pattern backtest...")
        backtest_doubles(strategy)
        ran = True
    if target in ("all", "triangles") and backtest_triangles:
        print("[*] Running triangles pattern backtest...")
        backtest_triangles(strategy)
        ran = True
    if target in ("all", "head_shoulders") and backtest_head_shoulders:
        print("[*] Running head-shoulders pattern backtest...")
        backtest_head_shoulders(strategy)
        ran = True
    if target in ("all", "wedges") and backtest_wedges:
        print("[*] Running wedges pattern backtest...")
        backtest_wedges(strategy)
        ran = True
    if not ran:
        print("[!] No backtest ran (perhaps module missing or typo in --target)")

if __name__ == "__main__":
    cli()
