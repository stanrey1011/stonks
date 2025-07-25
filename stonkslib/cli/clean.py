import click
import yaml
from pathlib import Path
from stonkslib.utils.logging import setup_logging
from stonkslib.clean.td import clean_td
from stonkslib.clean.od import clean_options_data

# Load configuration
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"

# Setup logging (fallback)
logger = setup_logging(PROJECT_ROOT / "log", "clean.log")

# Load config.yaml with error handling
try:
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)
    if config is None:
        raise ValueError("config.yaml is empty or invalid")
except FileNotFoundError:
    logger.error(f"[!] Config file not found at {CONFIG_PATH}")
    config = {
        "project": {
            "ticker_data_dir": "data/ticker_data/raw",
            "options_data_dir": "data/options_data/raw",
            "clean_ticker_dir": "data/ticker_data/clean",
            "clean_options_dir": "data/options_data/clean",
            "log_dir": "log"
        },
        "strategies": {
            "leaps_calls": {"min_dte": 365, "max_dte": 730, "side": "buy", "type": "calls"},
            "leaps_puts": {"min_dte": 365, "max_dte": 730, "side": "buy", "type": "puts"},
            "covered_calls": {"min_dte": 21, "max_dte": 45, "side": "sell", "type": "calls"},
            "secured_puts": {"min_dte": 21, "max_dte": 45, "side": "sell", "type": "puts"},
            "wheel": {"min_dte": 21, "max_dte": 45, "side": "sell", "type": "both"},
            "calendar_spread": {"min_dte": 30, "max_dte": 90, "side": "buy", "type": "calls"},
            "straddle": {"min_dte": 7, "max_dte": 45, "side": "buy", "type": "both"},
            "strangle": {"min_dte": 7, "max_dte": 45, "side": "buy", "type": "both"},
            "credit_spread": {"min_dte": 7, "max_dte": 45, "side": "sell", "type": "calls"},
            "iron_condor": {"min_dte": 7, "max_dte": 45, "side": "sell", "type": "both"}
        }
    }
except Exception as e:
    logger.error(f"[!] Error loading config.yaml: {e}")
    config = {
        "project": {
            "ticker_data_dir": "data/ticker_data/raw",
            "options_data_dir": "data/options_data/raw",
            "clean_ticker_dir": "data/ticker_data/clean",
            "clean_options_dir": "data/options_data/clean",
            "log_dir": "log"
        },
        "strategies": {}
    }

# Re-setup logging
logger = setup_logging(PROJECT_ROOT / config["project"]["log_dir"], "clean.log")

def load_tickers(yaml_file=TICKER_YAML):
    try:
        with open(yaml_file, "r") as f:
            data = yaml.safe_load(f)
        return data.get("stocks", []) + data.get("crypto", []) + data.get("etfs", [])
    except Exception as e:
        logger.error(f"[!] Failed to load tickers.yaml: {e}")
        return []

@click.group()
def clean():
    """Clean raw stock or options data."""

@clean.command()
@click.option("--force", is_flag=True, help="Force overwrite existing clean files")
@click.option("--ticker", type=str, default=None, help="Specific ticker to clean (default: all from tickers.yaml)")
@click.option(
    "--interval",
    type=click.Choice(["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]),
    default=None,
    help="Specific interval to clean (default: all intervals)"
)
def tickers(force, ticker, interval):
    """Clean stock, ETF, and crypto OHLC data."""
    tickers = [ticker] if ticker else load_tickers()
    intervals = [interval] if interval else ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]
    
    for t in tickers:
        for i in intervals:
            try:
                df = clean_td(t, i, force=force)
                if df is not None:
                    logger.info(f"[✓] Cleaned {t} ({i}) — {len(df)} rows")
                else:
                    logger.warning(f"[!] No data to clean for {t} ({i})")
            except Exception as e:
                logger.error(f"[!] Failed to clean {t} ({i}): {e}")

@clean.command()
@click.option("--force", is_flag=True, help="Force overwrite existing clean files")
@click.option("--ticker", type=str, default=None, help="Specific ticker to clean (default: all from tickers.yaml)")
@click.option(
    "--strategy",
    type=click.Choice(["leaps_calls", "leaps_puts", "covered_calls", "secured_puts", "wheel", "calendar_spread", "straddle", "strangle", "credit_spread", "iron_condor"]),
    default=None,
    help="Specific strategy to clean (default: all from config.yaml)"
)
@click.option(
    "--side",
    type=click.Choice(["buy", "sell"]),
    default=None,
    help="Buy or sell side for options (default: from config.yaml)"
)
@click.option(
    "--option_type",
    type=click.Choice(["calls", "puts"]),
    default=None,
    help="Option type (calls or puts, default: from config.yaml)"
)
def options(force, ticker, strategy, side, option_type):
    """Clean options data."""
    tickers = [ticker] if ticker else load_tickers()
    strategies = [strategy] if strategy else config.get("strategies", {}).keys()
    
    for t in tickers:
        for s in strategies:
            if s not in config.get("strategies", {}):
                logger.error(f"[!] Strategy {s} not in config.yaml")
                continue
            strategy_config = config["strategies"][s]
            effective_side = side if side else strategy_config.get("side", "buy")
            effective_type = option_type if option_type else strategy_config.get("type", "calls")
            if effective_type == "both" and s not in ["wheel", "straddle", "strangle", "iron_condor"]:
                logger.warning(f"[!] Strategy {s} does not support option_type 'both'")
                continue
            try:
                df = clean_options_data(t, s, side=effective_side, option_type=effective_type, force=force)
                if df is not None:
                    logger.info(f"[✓] Cleaned options {t} ({s}, {effective_side}, {effective_type}) — {len(df)} rows")
                else:
                    logger.warning(f"[!] No data to clean for options {t} ({s}, {effective_side}, {effective_type})")
            except Exception as e:
                logger.error(f"[!] Failed to clean options {t} ({s}, {effective_side}, {effective_type}): {e}")

if __name__ == "__main__":
    clean()