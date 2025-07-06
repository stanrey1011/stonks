import click
import pandas as pd
from pathlib import Path
import yaml
from stonkslib.utils.logging import setup_logging

# Load configuration
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

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
    config = {"project": {"ticker_data_dir": "data/ticker_data/raw", "options_data_dir": "data/options_data/raw", "log_dir": "log"}}
except Exception as e:
    logger.error(f"[!] Error loading config.yaml: {e}")
    config = {"project": {"ticker_data_dir": "data/ticker_data/raw", "options_data_dir": "data/options_data/raw", "log_dir": "log"}}

TICKER_RAW_DIR = PROJECT_ROOT / config["project"]["ticker_data_dir"]
TICKER_CLEAN_DIR = PROJECT_ROOT / config["project"]["ticker_data_dir"].replace("raw", "clean")
OPTIONS_RAW_DIR = PROJECT_ROOT / config["project"]["options_data_dir"]
OPTIONS_CLEAN_DIR = PROJECT_ROOT / config["project"]["options_data_dir"].replace("raw", "processed")
LOG_DIR = PROJECT_ROOT / config["project"]["log_dir"]

# Re-setup logging
logger = setup_logging(LOG_DIR, "clean.log")

STOCK_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]
OPTIONS_COLUMNS = ["expirationDate", "lastPrice", "strike", "daysToExpiration", "optionType"]

def clean_stock_data(ticker: str, interval: str, force: bool = False):
    input_path = TICKER_RAW_DIR / ticker / f"{interval}.csv"
    output_path = TICKER_CLEAN_DIR / ticker / f"{interval}.csv"

    if not input_path.exists():
        logger.warning(f"[!] Missing raw data: {input_path}")
        return None

    try:
        df = pd.read_csv(input_path, dtype=str)
        if not all(col in df.columns for col in STOCK_COLUMNS):
            logger.error(f"[!] Missing required columns in {input_path}")
            return None

        # Parse date column as UTC, drop unparseable
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
        df = df[df["Date"].notna()]
        df.set_index("Date", inplace=True)

        # Convert columns to numeric, drop non-numeric rows
        df = df[STOCK_COLUMNS[1:]].apply(pd.to_numeric, errors="coerce")
        df.dropna(subset=STOCK_COLUMNS[1:], inplace=True)
        df = df.drop_duplicates(keep="last")
        df = df.sort_index()

        if df.empty or df.index[0].year < 1980:
            logger.warning(f"[!] Data looks wrong after cleaning {ticker} ({interval})—please check raw file!")
            return None

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if force or not output_path.exists():
            df.to_csv(output_path)
            logger.info(f"[✓] Cleaned stock data: {ticker} ({interval}) → {output_path}")
        return df
    except Exception as e:
        logger.error(f"[!] Failed to clean {input_path}: {e}")
        return None

def clean_options_data(ticker: str, strategy: str, force: bool = False):
    input_path = OPTIONS_RAW_DIR / config["strategies"][strategy]["output_dir"] / f"{ticker}.csv"
    output_path = OPTIONS_CLEAN_DIR / config["strategies"][strategy]["output_dir"] / f"{ticker}.csv"

    if not input_path.exists():
        logger.warning(f"[!] Missing raw options data: {input_path}")
        return None

    try:
        df = pd.read_csv(input_path)
        if not all(col in df.columns for col in OPTIONS_COLUMNS):
            logger.error(f"[!] Missing required columns in {input_path}")
            return None

        # Parse expirationDate as UTC, drop unparseable
        df["expirationDate"] = pd.to_datetime(df["expirationDate"], errors="coerce", utc=True)
        df = df[df["expirationDate"].notna()]
        df.set_index("expirationDate", inplace=True)

        # Convert numeric columns, drop non-numeric rows
        numeric_cols = ["lastPrice", "strike", "daysToExpiration"]
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")
        df.dropna(subset=numeric_cols, inplace=True)
        df = df[OPTIONS_COLUMNS[1:]]
        df = df.drop_duplicates(subset=["strike", "optionType"], keep="last")
        df = df.sort_index()

        if df.empty:
            logger.warning(f"[!] No valid data after cleaning: {input_path}")
            return None

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if force or not output_path.exists():
            df.to_csv(output_path)
            logger.info(f"[✓] Cleaned options data: {ticker} ({strategy}) → {output_path}")
        return df
    except Exception as e:
        logger.error(f"[!] Failed to clean {input_path}: {e}")
        return None

@click.command()
@click.option(
    "--type",
    type=click.Choice(["stocks", "options"]),
    default="stocks",
    help="Data type to clean: stocks or options",
)
@click.option(
    "--strategy",
    type=click.Choice(["leaps", "covered_calls", "secured_puts"]),
    default=None,
    help="Strategy for options cleaning (required for options)",
)
@click.option("--ticker", type=str, default="AAPL", help="Ticker to clean (default: AAPL)")
@click.option(
    "--interval",
    type=click.Choice(["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]),
    default="1d",
    help="Interval for stock data (default: 1d)",
)
@click.option("--force", is_flag=True, help="Force overwrite of existing cleaned data")
def clean(type, strategy, ticker, interval, force):
    """Clean raw stock or options data."""
    if type == "options" and not strategy:
        logger.error("[!] --strategy must be specified for options cleaning")
        return

    if type == "stocks":
        clean_stock_data(ticker, interval, force)
    else:
        clean_options_data(ticker, strategy, force)

if __name__ == "__main__":
    clean()