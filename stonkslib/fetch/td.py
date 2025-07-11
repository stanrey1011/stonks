import os
import sys
import yaml
import pandas as pd
import yfinance as yf
from pathlib import Path
import warnings
import time

# Fix import path for guard.py and ranges.py
sys.path.append(str(Path(__file__).resolve().parent))
from guard import needs_update
from ranges import CATEGORY_INTERVALS
from stonkslib.utils.logging import setup_logging

# Suppress warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# Load configuration
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

# Setup logging (fallback)
logger = setup_logging(PROJECT_ROOT / "log", "fetch.log")

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
TICKER_YAML = PROJECT_ROOT / config["project"]["ticker_yaml"]
LOG_DIR = PROJECT_ROOT / config["project"]["log_dir"]

# Re-setup logging
logger = setup_logging(LOG_DIR, "fetch.log")

def fetch_all(yaml_file=TICKER_YAML, data_dir=TICKER_RAW_DIR, force=False, tickers=None, category=None):
    """Fetch stock data and save to ticker-centric directory structure."""
    yaml_path = Path(yaml_file)
    raw_data_path = Path(data_dir)
    with open(yaml_path, "r") as f:
        all_tickers = yaml.safe_load(f)
    logger.info(f"Available categories in YAML: {all_tickers.keys()}")

    if tickers is not None:
        target_tickers = tickers
        intervals = CATEGORY_INTERVALS.get(category or "stocks", [("1d", "1y")])
        cats = [category or "stocks"]
    elif category:
        cats = [category]
    else:
        cats = all_tickers.keys()

    for cat in cats:
        logger.info(f"Loading {cat} category...")
        if tickers is not None:
            these_tickers = target_tickers
        else:
            these_tickers = all_tickers.get(cat, [])
        logger.info(f"Loading {cat} tickers: {these_tickers}")
        intervals = CATEGORY_INTERVALS.get(cat, [("1d", "1y")])

        for ticker in these_tickers:
            for interval, period in intervals:
                interval_str = str(interval)
                csv_path = raw_data_path / ticker / f"{interval_str}.csv"

                if not force and not needs_update(csv_path, interval_str):
                    if csv_path.exists():
                        try:
                            existing = pd.read_csv(csv_path, index_col=0)
                            existing.index.name = "Date"
                            existing.index = pd.to_datetime(existing.index, utc=True, errors="coerce")
                            existing = existing[existing.index.notna()]
                            latest = existing.index[-1] if not existing.empty else "n/a"
                            logger.info(f"[⏭] Skipping {ticker} ({interval_str}) – {len(existing)} rows, latest: {latest}")
                        except Exception as e:
                            logger.error(f"[⏭] Skipping {ticker} ({interval_str}) – error reading existing data: {e}")
                    else:
                        logger.info(f"[⏭] Skipping {ticker} ({interval_str}) – file not found but considered fresh")
                    continue

                logger.info(f"[↑] Fetching {ticker} ({interval_str}, {period})...")
                try:
                    yf_interval = {"1h": "60m"}.get(interval_str, interval_str)
                    df = yf.download(ticker, interval=interval_str, period=period, progress=False)
                    if not df.empty:
                        df.index.name = "Date"
                        df.index = pd.to_datetime(df.index, utc=True)
                        csv_path.parent.mkdir(parents=True, exist_ok=True)
                        if force or not csv_path.exists():
                            df.to_csv(csv_path)
                            logger.info(f"[✓] Saved {ticker} → {interval_str} (new file, {len(df)} rows, latest: {df.index[-1]})")
                        else:
                            existing = pd.read_csv(csv_path, index_col=0)
                            existing.index.name = "Date"
                            existing.index = pd.to_datetime(existing.index, utc=True, errors="coerce")
                            existing = existing[existing.index.notna()]
                            new_rows = df[~df.index.isin(existing.index)]
                            if new_rows.empty:
                                logger.info(f"[⏭] Skipping {ticker} ({interval_str}) – already up-to-date")
                                continue
                            df = pd.concat([existing, new_rows])
                            df.sort_index(inplace=True)
                            df.to_csv(csv_path)
                            logger.info(f"[✓] Appended {len(new_rows)} rows to {ticker} → {interval_str}, latest: {df.index[-1]})")
                    else:
                        logger.warning(f"[!] No data for {ticker} ({interval_str})")
                    # Add delay to avoid hitting yfinance rate limits
                    time.sleep(0.5)  # 0.5 seconds per request
                except Exception as e:
                    logger.error(f"[!] Error fetching {ticker} ({interval_str}): {e}")

if __name__ == "__main__":
    fetch_all()