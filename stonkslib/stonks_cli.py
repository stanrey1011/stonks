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
from stonkslib.fetch.options.generic import fetch_all_options


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

def load_tickers(category=None, yaml_file=TICKER_YAML):
    with open(yaml_file, "r") as f:
        data = yaml.safe_load(f)
    if category:
        return data.get(category, [])
    # All by default:
    return data.get("stocks", []) + data.get("crypto", []) + data.get("etfs", [])

@click.group()
def cli():
    """Stonks CLI"""

# ========================== FETCH GROUP ==========================
@cli.group()
def fetch():
    """Fetch raw data (OHLCV, options, etc)."""

# --- Fetch OHLC/price data: stocks, etf, crypto ---
@fetch.command("stocks")
@click.option("--force", is_flag=True, help="Force re-download and overwrite existing CSVs")
def fetch_stocks(force):
    """Fetch all stock OHLCV data."""
    fetch_all(force=force, category="stocks")

@fetch.command("etfs")
@click.option("--force", is_flag=True, help="Force re-download and overwrite existing CSVs")
def fetch_etf(force):
    """Fetch all ETF OHLCV data."""
    fetch_all(force=force, category="etfs")

@fetch.command("crypto")
@click.option("--force", is_flag=True, help="Force re-download and overwrite existing CSVs")
def fetch_crypto(force):
    """Fetch all crypto OHLCV data."""
    fetch_all(force=force, category="crypto")

# ================== FETCH OPTIONS NESTED GROUPS ==================
@fetch.group()
def options():
    """Fetch option chains."""

@options.group()
def buy():
    """Buy side options."""

@options.group()
def sell():
    """Sell side options."""

# Buy side: calls & puts
@buy.command("calls")
@click.argument("term", type=click.Choice(["leaps", "weekly", "monthly", "custom"]))
@click.option("--ticker", type=str, default=None)
def buy_calls(term, ticker):
    run_options_fetch("buy", "calls", term, ticker)

@buy.command("puts")
@click.argument("term", type=click.Choice(["leaps", "weekly", "monthly", "custom"]))
@click.option("--ticker", type=str, default=None)
def buy_puts(term, ticker):
    run_options_fetch("buy", "puts", term, ticker)

# Sell side: calls & puts
@sell.command("calls")
@click.argument("term", type=click.Choice(["leaps", "weekly", "monthly", "custom"]))
@click.option("--ticker", type=str, default=None)
def sell_calls(term, ticker):
    run_options_fetch("sell", "calls", term, ticker)

@sell.command("puts")
@click.argument("term", type=click.Choice(["leaps", "weekly", "monthly", "custom"]))
@click.option("--ticker", type=str, default=None)
def sell_puts(term, ticker):
    run_options_fetch("sell", "puts", term, ticker)

def run_options_fetch(side, option_type, term, ticker):
    # DTE logic
    if term == "leaps":
        min_dte, max_dte = 270, 9999
    elif term == "weekly":
        min_dte, max_dte = 7, 13
    elif term == "monthly":
        min_dte, max_dte = 30, 45
    else:
        min_dte, max_dte = 0, 9999

    output_dir = os.path.join(
        "data", "options_data", "raw",
        option_type, side, term
    )

    # Determine ticker(s)
    def ticker_list():
        if ticker:
            return [ticker]
        import yaml
        PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        TICKER_YAML = os.path.join(PROJECT_ROOT, "tickers.yaml")
        with open(TICKER_YAML, "r") as f:
            tickers = yaml.safe_load(f)
        cats = ["stocks", "etfs"]
        return [sym for cat in cats for sym in tickers.get(cat, [])]

    fetch_all_options(
        output_dir=output_dir,
        min_days_out=min_dte,
        max_days_out=max_dte,
        option_type=option_type,
        symbols=ticker_list()
    )
    print(f"[✓] Options data saved to {output_dir}/<TICKER>.csv")

# ========================== REST OF CLI ==========================
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
@click.option(
    "--ticker",
    type=str,
    default=None,
    help="Limit merging to a specific ticker",
)
@click.option(
    "--interval",
    type=str,
    default=None,
    help="Limit merging to a specific interval",
)
def merge_cmd(target, ticker, interval):
    """Merge signals into combined time series format"""
    if target in ("indicators", "all"):
        if ticker and interval:
            from stonkslib.merge.by_indicators import merge_signals_for_ticker_interval
            merge_signals_for_ticker_interval(ticker, interval)
        else:
            from stonkslib.merge.by_indicators import run_merge_indicators
            run_merge_indicators()

    if target in ("patterns", "all"):
        if ticker and interval:
            from stonkslib.merge.by_patterns import merge_patterns_for_ticker_interval
            merge_patterns_for_ticker_interval(ticker, interval)
        else:
            from stonkslib.merge.by_patterns import run_merge_patterns
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
