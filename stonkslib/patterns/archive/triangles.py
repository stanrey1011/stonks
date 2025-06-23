# stonkslib/patterns/triangles.py

import logging
import pandas as pd
from stonkslib.utils import load_ticker_data

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def find_triangle_patterns(ticker, category, interval, window=5, lookback=60):
    """
    Detect triangle chart patterns from OHLC data.
    """
    # Ensure that interval is a string
    if not isinstance(interval, str):
        interval = str(interval)  # Convert to string if it's not
    
    try:
        # Load data using the updated load_ticker_data function
        df = load_ticker_data(ticker, base_dir="data/ticker_data", interval=interval)
    except FileNotFoundError as e:
        log.warning(f"[!] {e}")
        return []

    df = df.sort_index().copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"]).copy()
    df = df.tail(lookback)

    if df.empty or "Close" not in df.columns:
        return []

    # Add logic for detecting the triangle pattern (if needed)
    # Example logic, replace with actual pattern detection logic

    patterns = []  # Store detected patterns
    return patterns
