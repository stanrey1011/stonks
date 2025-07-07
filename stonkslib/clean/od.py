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
    print(f"[!] Config file not found at {CONFIG_PATH}. Using defaults.")
    config = {"project": {"ticker_data_dir": "data/ticker_data/raw", "log_dir": "log"}}
except Exception as e:
    logger.error(f"[!] Error loading config.yaml: {e}")
    print(f"[!] Error loading config.yaml: {e}. Using defaults.")
    config = {"project": {"ticker_data_dir": "data/ticker_data/raw", "log_dir": "log"}}

TICKER_RAW_DIR = PROJECT_ROOT / config["project"]["ticker_data_dir"]
TICKER_CLEAN_DIR = PROJECT_ROOT / config["project"]["ticker_data_dir"].replace("raw", "clean")
LOG_DIR = PROJECT_ROOT / config["project"]["log_dir"]

# Re-setup logging
logger = setup_logging(LOG_DIR, "clean.log")

STOCK_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]

def clean_stock_data(ticker: str, interval: str, force: bool = False):
    """Clean raw stock data and save to ticker-centric directory."""
    input_path = TICKER_RAW_DIR / ticker / f"{interval}.csv"
    output_path = TICKER_CLEAN_DIR / ticker / f"{interval}.csv"

    logger.info(f"[>] Checking input file: {input_path}")
    if not input_path.exists():
        logger.warning(f"[!] Missing raw data: {input_path}")
        print(f"[!] Missing raw data: {input_path}")
        return None

    try:
        logger.info(f"[>] Reading {input_path}")
        df = pd.read_csv(input_path, dtype=str)
        if not all(col in df.columns for col in STOCK_COLUMNS):
            logger.error(f"[!] Missing required columns in {input_path}")
            print(f"[!] Missing required columns in {input_path}")
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
            print(f"[!] Data looks wrong after cleaning {ticker} ({interval})—please check raw file!")
            return None

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if force or not output_path.exists():
            df.to_csv(output_path)
            logger.info(f"[✓] Cleaned stock data: {ticker} ({interval}) → {output_path}")
            print(f"[✓] Cleaned stock data: {ticker} ({interval}) → {output_path}")
        else:
            logger.info(f"[⏭] Output file exists and force=False: {output_path}")
            print(f"[⏭] Output file exists and force=False: {output_path}")
        return df
    except Exception as e:
        logger.error(f"[!] Failed to clean {input_path}: {e}")
        print(f"[!] Failed to clean {input_path}: {e}")
        return None

if __name__ == "__main__":
    logger.info("[>] Starting test clean for QQQ (1wk)")
    print("[>] Starting test clean for QQQ (1wk)")
    result = clean_stock_data(ticker="QQQ", interval="1wk", force=False)
    if result is not None:
        logger.info(f"[✓] Test clean successful: QQQ (1wk), {len(result)} rows")
        print(f"[✓] Test clean successful: QQQ (1wk), {len(result)} rows")
    else:
        logger.warning("[!] Test clean failed for QQQ (1wk)")
        print("[!] Test clean failed for QQQ (1wk)")