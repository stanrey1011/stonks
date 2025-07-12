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
    config = {"project": {"options_data_dir": "data/options_data/raw", "log_dir": "log"}, "strategies": {}}
except Exception as e:
    logger.error(f"[!] Error loading config.yaml: {e}")
    config = {"project": {"options_data_dir": "data/options_data/raw", "log_dir": "log"}, "strategies": {}}

OPTIONS_RAW_DIR = PROJECT_ROOT / config["project"]["options_data_dir"]
OPTIONS_CLEAN_DIR = PROJECT_ROOT / config["project"]["options_data_dir"].replace("raw", "clean")
LOG_DIR = PROJECT_ROOT / config["project"]["log_dir"]

# Re-setup logging
logger = setup_logging(LOG_DIR, "clean.log")

OPTIONS_COLUMNS = ["expirationDate", "lastPrice", "strike", "daysToExpiration", "optionType", "impliedVolatility", "volume", "openInterest", "bid", "ask"]

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

        # Parse dates as UTC
        df["expirationDate"] = pd.to_datetime(df["expirationDate"], errors="coerce", utc=True)
        df = df[df["expirationDate"].notna()]
        df.set_index("expirationDate", inplace=True)

        # Convert numeric columns
        numeric_cols = ["lastPrice", "strike", "daysToExpiration", "impliedVolatility", "volume", "openInterest", "bid", "ask"]
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")
        df = df.dropna(subset=numeric_cols)

        # Fill missing volume/openInterest with zero
        df["volume"] = df["volume"].fillna(0)
        df["openInterest"] = df["openInterest"].fillna(0)

        # Drop duplicates
        df = df.drop_duplicates(subset=["strike", "optionType"], keep="last")
        df = df.sort_index()

        # Add strategy label from config.yaml
        df["strategy"] = strategy

        # Calculate IV rank
        if "impliedVolatility" in df.columns and len(df) > 1:
            iv_min = df["impliedVolatility"].min()
            iv_max = df["impliedVolatility"].max()
            df["iv_rank"] = (df["impliedVolatility"] - iv_min) / (iv_max - iv_min + 1e-6) * 100

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