# @pattern_module: false

import os
import pandas as pd
import logging
from collections import defaultdict
from stonkslib.patterns.head_shoulders import find_head_shoulders_patterns
from stonkslib.patterns.doubles import find_double_patterns
from stonkslib.patterns.triangles import find_triangle_patterns
from stonkslib.patterns.wedges import find_wedge_patterns

# Constants
DEBUG_MODE = True
MAX_PER_PATTERN = 5
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ticker_data")

# Configure logging
logging.basicConfig(
    format='[%(levelname)s] %(message)s',
    level=logging.DEBUG if DEBUG_MODE else logging.INFO
)
logger = logging.getLogger(__name__)

# Pattern weightings
PATTERN_SCORES = {
    "Head & Shoulders": -20,
    "Double Top": -20,
    "Rising Wedge": -20,
    "Symmetrical Triangle": 0,
    "Descending Triangle": -10,
    "Ascending Triangle": +10,
    "Inverse H&S": +20,
    "Double Bottom": +20,
    "Falling Wedge": +20,
}

def get_latest_date(ticker):
    file_path = os.path.join(DATA_DIR, f"{ticker}.csv")
    try:
        df = pd.read_csv(file_path, parse_dates=["Date"])
        return df["Date"].max().date()
    except Exception:
        return "N/A"

def calculate_pattern_score(ticker):
    score = 0
    pattern_log = []
    seen_counts = defaultdict(int)

    for find_func in [
        find_head_shoulders_patterns,
        find_double_patterns,
        find_triangle_patterns,
        find_wedge_patterns
    ]:
        try:
            patterns = find_func(ticker)
        except Exception as e:
            logging.info(f"[!] Error processing {ticker} in {find_func.__name__}: {e}")
            continue

        for start, end, pattern_type, confidence in patterns:
            try:
                confidence = float(confidence)
            except (ValueError, TypeError):
                logging.info(f"[!] Invalid confidence '{confidence}' for {pattern_type} → skipping")
                continue

            if confidence < 0.2:
                continue

            if seen_counts[pattern_type] >= MAX_PER_PATTERN:
                continue
            seen_counts[pattern_type] += 1

            weight = PATTERN_SCORES.get(pattern_type, 0)
            contribution = round(confidence * weight)
            logger.debug(f"{pattern_type} → confidence={confidence}, weight={weight}, contribution={contribution}")
            score += contribution
            pattern_log.append((start.date(), end.date(), pattern_type, confidence, contribution))

    return score, pattern_log

if __name__ == "__main__":
    from tabulate import tabulate
    from datetime import datetime
    from stonkslib.data_collection.fetch_data import load_tickers

    print("\n📊 Pattern Scores\n" + "-" * 40)
    tickers = load_tickers()
    all_tickers = tickers["stocks"] + tickers["crypto"] + tickers["etfs"]

    results = []
    today = datetime.today().date()

    for ticker in all_tickers:
        score, pattern_log = calculate_pattern_score(ticker)
        signal = (
            "STRONG BEARISH" if score <= -150 else
            "BEARISH" if score < -50 else
            "NEUTRAL" if -50 <= score <= 50 else
            "BULLISH" if score < 150 else
            "STRONG BULLISH"
        )
        results.append([ticker, score, signal, today])

    # Output once at the end
    print("\n📊 Summary\n" + "-" * 40)
    print(tabulate(results, headers=["Ticker", "Score", "Signal", "Date"], tablefmt="fancy_grid"))
