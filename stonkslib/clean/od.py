import pandas as pd
from pathlib import Path
from stonkslib.utils.logging import setup_logging

PROJECT_ROOT = Path(__file__).resolve().parents[3]
logger = setup_logging(PROJECT_ROOT / "log", "clean.log")

def clean_options_data(ticker: str, strategy: str, side: str, option_type: str, force: bool = False, debug: bool = False):
    """Clean raw options data and save to strategy-centric directory."""
    # Handle special case for leaps/options/ subdirectory
    input_path = PROJECT_ROOT / "data/options_data/raw" / side / strategy / option_type / f"{ticker}.csv"
    if strategy == "leaps" and not input_path.exists():
        input_path = PROJECT_ROOT / "data/options_data/raw" / side / strategy / "options" / f"{ticker}.csv"
    output_path = PROJECT_ROOT / "data/options_data/clean" / side / strategy / option_type / f"{ticker}.csv"
    logger.info(f"[>] Checking input file: {input_path}")
    if not input_path.exists():
        logger.warning(f"[!] Missing raw options data: {input_path}")
        return None
    try:
        df = pd.read_csv(input_path, parse_dates=['expiration', 'last_trade_date'], errors="coerce")
        required_columns = ['strike', 'bid', 'ask', 'volume', 'open_interest', 'expiration']
        if not all(col in df.columns for col in required_columns):
            logger.error(f"[!] Missing required columns in {input_path}: expected {required_columns}, got {list(df.columns)}")
            return None
        df['expiration'] = pd.to_datetime(df['expiration'], errors="coerce", utc=True)
        df['last_trade_date'] = pd.to_datetime(df['last_trade_date'], errors="coerce", utc=True)
        df = df[df['expiration'].notna()]
        numeric_cols = ['strike', 'bid', 'ask', 'volume', 'open_interest']
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")
        df.dropna(subset=numeric_cols, inplace=True)
        df = df.drop_duplicates(subset=['strike', 'expiration'], keep='last')
        df = df.sort_values('expiration')
        if df.empty:
            logger.warning(f"[!] No valid data after cleaning {ticker} ({strategy}, {side}, {option_type})")
            return None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if force or not output_path.exists():
            df.to_csv(output_path, index=False)
            logger.info(f"[✓] Cleaned options data: {ticker} ({strategy}, {side}, {option_type}) → {output_path}")
        return df
    except Exception as e:
        logger.error(f"[!] Failed to clean {input_path}: {e}")
        return None