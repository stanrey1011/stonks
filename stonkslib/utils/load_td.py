from pathlib import Path
import pandas as pd

# Automatically resolve project root relative to this file
BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CLEAN_DIR = BASE_DIR / "data" / "ticker_data" / "clean"

def load_td(tickers: list[str], interval: str, base_dir: Path = DEFAULT_CLEAN_DIR) -> dict[str, pd.DataFrame | None]:
    """
    Load cleaned CSVs into memory for LLMs or analysis.

    Args:
        tickers (list): List of ticker symbols
        interval (str): Timeframe like '1d', '1wk', '1m'
        base_dir (Path): Base path to cleaned data

    Returns:
        dict: Dictionary of DataFrames keyed by ticker; None if missing/invalid
    """
    data = {}
    for ticker in tickers:
        ticker_path = base_dir / ticker  # Fixed: {ticker} first
        file_path = ticker_path / f"{interval}.csv"  # Now clean/{ticker}/{interval}.csv
        if not file_path.exists():
            print(f"[!] Missing cleaned file: {ticker} ({interval}) at {file_path}")
            data[ticker] = None  # Explicit None for graceful handling
            continue

        try:
            df = pd.read_csv(file_path, index_col=0, parse_dates=True)
            df = df.sort_index()
            data[ticker] = df
        except Exception as e:
            print(f"[!] Failed to load {file_path}: {e}")
            data[ticker] = None

    return data