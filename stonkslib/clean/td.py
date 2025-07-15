import pandas as pd
from pathlib import Path
import yaml
from stonkslib.utils.logging import setup_logging

# Load configuration (moved to a util if shared across modules)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"

logger = setup_logging(PROJECT_ROOT / "log", "clean.log")

try:
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)
    if config is None:
        raise ValueError("config.yaml is empty or invalid")
except Exception as e:
    logger.error(f"[!] Error loading config: {e}")
    config = {"project": {"ticker_data_dir": "data/ticker_data/raw", "log_dir": "log"}}

TICKER_RAW_DIR = PROJECT_ROOT / config["project"]["ticker_data_dir"]
TICKER_CLEAN_DIR = TICKER_RAW_DIR.parent / "clean"  # Simplified from replace for clarity
LOG_DIR = PROJECT_ROOT / config["project"]["log_dir"]

STOCK_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]
INTERVALS = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]

def clean_td(ticker: str, interval: str, force: bool = False, debug: bool = False) -> pd.DataFrame | None:
    """Clean raw ticker data and save to ticker-centric directory. Returns cleaned DF for modularity."""
    input_path = TICKER_RAW_DIR / ticker / f"{interval}.csv"
    output_path = TICKER_CLEAN_DIR / ticker / f"{interval}.csv"

    if debug:
        print(f"[>] Checking {input_path}")
    if not input_path.exists():
        logger.warning(f"[!] Missing raw data: {input_path}")
        return None

    try:
        df = pd.read_csv(input_path, skiprows=[1, 2], dtype=str)
        df.columns = df.columns.str.lower()  # Case-insensitive
        if 'price' in df.columns:
            df.rename(columns={'price': 'date'}, inplace=True)

        required_cols = [col.lower() for col in STOCK_COLUMNS]
        if not all(col in df.columns for col in required_cols):
            logger.error(f"[!] Missing columns: expected {required_cols}, got {list(df.columns)}")
            return None

        df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True)
        df = df[df["date"].notna()].set_index("date")

        df = df[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="coerce")
        df.dropna(inplace=True)
        df = df.drop_duplicates(keep="last").sort_index()

        if df.empty or df.index[0].year < 1980:
            logger.warning(f"[!] Invalid data after cleaning {ticker} ({interval})")
            return None

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if force or not output_path.exists():
            df.to_parquet(output_path.with_suffix('.parquet'))  # Switch to Parquet for efficiency
            logger.info(f"[✓] Cleaned: {output_path}")
        return df  # Return DF for chaining/modularity
    except Exception as e:
        logger.error(f"[!] Failed: {e}")
        return None

# Optional test block (comment out or env-gate for production)
if __name__ == "__main__" and os.environ.get("RUN_TEST_CLEAN"):
    try:
        with open(TICKER_YAML, "r") as f:
            all_tickers = yaml.safe_load(f)
        tickers = [ticker for category in all_tickers for ticker in all_tickers[category]]
    except Exception:
        tickers = ["QQQ"]
    for ticker in tickers:
        for interval in INTERVALS:
            result = clean_td(ticker, interval, debug=True)
            if result is not None:
                print(f"[✓] Success: {ticker} ({interval}), {len(result)} rows")