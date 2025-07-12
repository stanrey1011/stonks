import pandas as pd
from pathlib import Path
from stonkslib.utils.logging import setup_logging

# Load configuration
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"

# Setup logging
logger = setup_logging(PROJECT_ROOT / "log", "clean.log")

def clean_options_data(ticker: str, strategy: str, force: bool = False, debug: bool = False):
    """Clean raw options data and save to strategy-centric directory."""
    input_path = PROJECT_ROOT / "data/options_data/raw" / strategy / f"{ticker}.csv"
    output_path = PROJECT_ROOT / "data/options_data/clean" / strategy / f"{ticker}.csv"

    logger.info(f"[>] Checking input file: {input_path}")
    if debug:
        print(f"[>] Checking input file: {input_path}")
    if not input_path.exists():
        logger.warning(f"[!] Missing raw options data: {input_path}")
        if debug:
            print(f"[!] Missing raw options data: {input_path}")
        return None

    try:
        logger.info(f"[>] Reading {input_path}")
        if debug:
            print(f"[>] Reading {input_path}")
        df = pd.read_csv(input_path, parse_dates=['expiration', 'last_trade_date'], errors="coerce")
        
        # Expected columns for options data (adjust based on your fetch_all_options output)
        required_columns = ['strike', 'bid', 'ask', 'volume', 'open_interest', 'expiration']
        if not all(col in df.columns for col in required_columns):
            logger.error(f"[!] Missing required columns in {input_path}: expected {required_columns}, got {list(df.columns)}")
            if debug:
                print(f"[!] Missing required columns in {input_path}: expected {required_columns}, got {list(df.columns)}")
            return None

        # Clean dates and drop unparseable
        df['expiration'] = pd.to_datetime(df['expiration'], errors="coerce", utc=True)
        df['last_trade_date'] = pd.to_datetime(df['last_trade_date'], errors="coerce", utc=True)
        df = df[df['expiration'].notna()]

        # Convert numeric columns
        numeric_cols = ['strike', 'bid', 'ask', 'volume', 'open_interest']
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")
        df.dropna(subset=numeric_cols, inplace=True)

        # Remove duplicates and sort by expiration
        df = df.drop_duplicates(subset=['strike', 'expiration'], keep='last')
        df = df.sort_values('expiration')

        if df.empty:
            logger.warning(f"[!] No valid data after cleaning {ticker} ({strategy})")
            if debug:
                print(f"[!] No valid data after cleaning {ticker} ({strategy})")
            return None

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if force or not output_path.exists():
            df.to_csv(output_path, index=False)
            logger.info(f"[✓] Cleaned options data: {ticker} ({strategy}) → {output_path}")
            if debug:
                print(f"[✓] Cleaned options data: {ticker} ({strategy}) → {output_path}")
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
    # Example test
    logger.info("[>] Testing options data cleaning")
    result = clean_options_data("QQQ", "leaps", debug=True)
    if result is not None:
        logger.info(f"[✓] Test clean successful: QQQ (leaps), {len(result)} rows")
    else:
        logger.warning("[!] Test clean failed for QQQ (leaps)")