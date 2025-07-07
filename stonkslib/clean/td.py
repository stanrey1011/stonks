import pandas as pd
from pathlib import Path
import yaml
from stonkslib.utils.logging import setup_logging

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
    config = {"project": {"ticker_data_dir": "data/ticker_data/raw", "log_dir": "log"}}
except Exception as e:
    logger.error(f"[!] Error loading config.yaml: {e}")
    config = {"project": {"ticker_data_dir": "data/ticker_data/raw", "log_dir": "log"}}

TICKER_RAW_DIR = PROJECT_ROOT / config["project"]["ticker_data_dir"]
TICKER_CLEAN_DIR = PROJECT_ROOT / config["project"]["ticker_data_dir"].replace("raw", "clean")
LOG_DIR = PROJECT_ROOT / config["project"]["log_dir"]

# Re-setup logging
logger = setup_logging(LOG_DIR, "clean.log")

STOCK_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]
INTERVALS = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]

def clean_stock_data(ticker: str, interval: str, force: bool = False, debug: bool = False):
    """Clean raw stock data and save to ticker-centric directory."""
    input_path = TICKER_RAW_DIR / ticker / f"{interval}.csv"
    output_path = TICKER_CLEAN_DIR / ticker / f"{interval}.csv"

    logger.info(f"[>] Checking input file: {input_path}")
    if debug:
        print(f"[>] Checking input file: {input_path}")
    if not input_path.exists():
        logger.warning(f"[!] Missing raw data: {input_path}")
        if debug:
            print(f"[!] Missing raw data: {input_path}")
        return None

    try:
        logger.info(f"[>] Reading {input_path}")
        if debug:
            print(f"[>] Reading {input_path}")
        # Read CSV, skipping bad header rows and renaming 'Price' to 'Date'
        df = pd.read_csv(input_path, skiprows=[1, 2], dtype=str)
        if 'Price' in df.columns:
            df.rename(columns={'Price': 'Date'}, inplace=True)
        else:
            logger.error(f"[!] 'Price' or 'Date' column missing in {input_path}")
            if debug:
                print(f"[!] 'Price' or 'Date' column missing in {input_path}")
            return None

        if not all(col in df.columns for col in STOCK_COLUMNS):
            logger.error(f"[!] Missing required columns in {input_path}: expected {STOCK_COLUMNS}, got {list(df.columns)}")
            if debug:
                print(f"[!] Missing required columns in {input_path}: expected {STOCK_COLUMNS}, got {list(df.columns)}")
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
            if debug:
                print(f"[!] Data looks wrong after cleaning {ticker} ({interval})—please check raw file!")
            return None

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if force or not output_path.exists():
            df.to_csv(output_path)
            logger.info(f"[✓] Cleaned stock data: {ticker} ({interval}) → {output_path}")
            if debug:
                print(f"[✓] Cleaned stock data: {ticker} ({interval}) → {output_path}")
        else:
            logger.info(f"[⏭] Output file exists and force=False: {output_path}")
            if debug:
                print(f"[⏭] Output file exists and force=False: {output_path}")
        return df
    except Exception as e:
        logger.error(f"[!] Failed to clean {input_path}: {e}")
        if debug:
            print(f"[!] Failed to clean {input_path}: {e}")
        return None

if __name__ == "__main__":
    # Load tickers from tickers.yaml
    try:
        with open(TICKER_YAML, "r") as f:
            all_tickers = yaml.safe_load(f)
        tickers = []
        for category in all_tickers:
            tickers.extend(all_tickers[category])
    except Exception as e:
        logger.error(f"[!] Failed to load tickers.yaml: {e}")
        print(f"[!] Failed to load tickers.yaml: {e}")
        tickers = ["QQQ"]  # Fallback to QQQ

    logger.info("[>] Starting test clean for all tickers")
    print("[>] Starting test clean for all tickers")
    for ticker in tickers:
        for interval in INTERVALS:
            logger.info(f"[>] Testing {ticker} ({interval})")
            print(f"[>] Testing {ticker} ({interval})")
            result = clean_stock_data(ticker=ticker, interval=interval, force=False, debug=True)
            if result is not None:
                logger.info(f"[✓] Test clean successful: {ticker} ({interval}), {len(result)} rows")
                print(f"[✓] Test clean successful: {ticker} ({interval}), {len(result)} rows")
            else:
                logger.warning(f"[!] Test clean failed for {ticker} ({interval})")
                print(f"[!] Test clean failed for {ticker} ({interval})")