import click
import yaml
from pathlib import Path
from stonkslib.utils.load_strategy import load_strategy_config
from stonkslib.utils.logging import setup_logging
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

# Load configuration
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

# Setup logging (fallback)
logger = setup_logging(PROJECT_ROOT / "log", "backtest.log")

# Load config.yaml with error handling
try:
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)
    if config is None:
        raise ValueError("config.yaml is empty or invalid")
except FileNotFoundError:
    logger.error(f"[!] Config file not found at {CONFIG_PATH}")
    config = {"project": {"ticker_data_dir": "data/ticker_data/raw", "options_data_dir": "data/options_data/raw", "backtest_dir": "data/backtest_results", "log_dir": "log"}}
except Exception as e:
    logger.error(f"[!] Error loading config.yaml: {e}")
    config = {"project": {"ticker_data_dir": "data/ticker_data/raw", "options_data_dir": "data/options_data/raw", "backtest_dir": "data/backtest_results", "log_dir": "log"}}

TICKER_DATA_DIR = PROJECT_ROOT / config["project"]["ticker_data_dir"]
OPTIONS_DATA_DIR = PROJECT_ROOT / config["project"]["options_data_dir"]
BACKTEST_DIR = PROJECT_ROOT / config["project"]["backtest_dir"]
LOG_DIR = PROJECT_ROOT / config["project"]["log_dir"]

# Re-setup logging
logger = setup_logging(LOG_DIR, "backtest.log")

@click.command()
@click.option(
    "--type",
    type=click.Choice(["stocks", "options"]),
    default="stocks",
    help="Backtest type: stocks or options",
)
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
    help="Path to strategy YAML config file (default: use config.yaml strategies)",
)
@click.option(
    "--strategy",
    type=click.Choice(["leaps", "covered_calls", "secured_puts"]),
    default=None,
    help="Strategy to backtest (required for options, default: all from config.yaml for stocks)",
)
@click.option("--ticker", type=str, default="AAPL", help="Ticker to backtest (default: AAPL)")
def backtest(type, target, config, strategy, ticker):
    """Run backtests on stock or options data."""
    strategy_config = load_strategy_config(config) if config else None
    if type == "options" and not strategy:
        logger.error("[!] --strategy must be specified for options backtests")
        return

    strategies_to_run = [strategy] if strategy else config.get("strategies", {}).keys()
    output_base = BACKTEST_DIR / type

    ran = False
    for strat in strategies_to_run:
        strat_config = config.get("strategies", {}).get(strat, strategy_config)
        if not strat_config:
            logger.error(f"[!] No config for strategy {strat}, skipping...")
            continue

        output_dir = output_base / strat if type == "options" else output_base

        if target in ("all", "indicators"):
            logger.info(f"[*] Running indicator backtest for {strat} on {ticker} ({type})...")
            backtest_indicators(None, strat_config, ticker, output_dir)
            ran = True
        if target in ("all", "doubles") and backtest_doubles:
            logger.info(f"[*] Running doubles pattern backtest for {strat} on {ticker} ({type})...")
            backtest_doubles(None, strat_config, ticker, output_dir)
            ran = True
        if target in ("all", "triangles") and backtest_triangles:
            logger.info(f"[*] Running triangles pattern backtest for {strat} on {ticker} ({type})...")
            backtest_triangles(None, strat_config, ticker, output_dir)
            ran = True
        if target in ("all", "head_shoulders") and backtest_head_shoulders:
            logger.info(f"[*] Running head-shoulders pattern backtest for {strat} on {ticker} ({type})...")
            backtest_head_shoulders(None, strat_config, ticker, output_dir)
            ran = True
        if target in ("all", "wedges") and backtest_wedges:
            logger.info(f"[*] Running wedges pattern backtest for {strat} on {ticker} ({type})...")
            backtest_wedges(None, strat_config, ticker, output_dir)
            ran = True

    if not ran:
        logger.error("[!] No backtest ran (perhaps module missing or typo in --target)")