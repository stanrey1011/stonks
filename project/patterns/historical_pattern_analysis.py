import os
import pandas as pd
import yaml
from datetime import timedelta
from project.patterns.head_shoulders import detect_head_shoulders_patterns
from project.patterns.doubles import detect_double_patterns
from project.patterns.triangles import detect_triangle_patterns
from project.patterns.wedges import detect_wedge_patterns
from project.utils import load_ticker_data

DEBUG = False
DEBUG_PRINT_PATTERNS = False
CONFIDENCE_THRESHOLD = 0.8
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "ticker_data")

def load_tickers_from_yaml():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  # ~/stonks/
    file_path = os.path.join(base_dir, "tickers.yaml")
    with open(file_path, "r") as f:
        data = yaml.safe_load(f)
#    return data.get("tickers", [])
    tickers = []
    for category in data.values():
        if isinstance(category, list):
            tickers.extend(category)
        if DEBUG:
            print(f"[DEBUG] Loaded tickers: {tickers}")
    return tickers


#def load_tickers_from_yaml(file_path="tickers.yaml"):
#    with open(file_path, "r") as f:
#        data = yaml.safe_load(f)
#    return data.get("tickers", [])

#TICKERS = ["AAPL", "MSFT", "TSLA", "NVDA", "BTC-USD", "ETH-USD", "SPY", "QQQ"]
TICKERS = load_tickers_from_yaml()
if DEBUG:
    print(f"[DEBUG] Loaded tickers: {TICKERS}")


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

WINDOW_SIZE = 60  # days per window
SWING_PERIODS = [7, 14, 21, 28]  # days after pattern ends to evaluate

def evaluate_swing_outcome(df, end_date, swing_days):
    try:
        end_idx = df.index.get_loc(end_date)
        future_idx = end_idx + swing_days
        if future_idx >= len(df):
            return None  # Not enough data
        future_price = df.iloc[future_idx]["Close"]
        current_price = df.iloc[end_idx]["Close"]
        return round((future_price - current_price) / current_price * 100, 2)  # % change
    except Exception:
        return None

def scan_ticker(ticker):
    print(f"[↑] Running historical pattern scan for {ticker}")
    try:
        if DEBUG:
            print(f"[DEBUG] Scanning: {ticker}")
        df = load_ticker_data(ticker)
        if DEBUG:
            print(f"[DEBUG] DataFrame for {ticker}: {df.shape}, columns: {df.columns}")
        results = []

        patterns = []
        patterns += detect_head_shoulders_patterns(ticker, df=df)
        patterns += detect_head_shoulders_patterns(ticker, inverse=True, df=df)
        patterns += detect_double_patterns(ticker, type="top", df=df)
        patterns += detect_double_patterns(ticker, type="bottom", df=df)
        patterns += detect_triangle_patterns(ticker, df=df)
        patterns += detect_wedge_patterns(ticker, df=df)

        for start, end, pattern_type, confidence in patterns:
            if DEBUG_PRINT_PATTERNS:
                print(f"[DEBUG] Found pattern: {pattern_type} ({ticker}) from {start} to {end} with confidence {confidence}")
            #Comment the next two for testing
            if confidence < CONFIDENCE_THRESHOLD:
                continue
            score = PATTERN_SCORES.get(pattern_type, 0)
            swings = {}
            for days in SWING_PERIODS:
                swing_return = evaluate_swing_outcome(df, end, days)
                if swing_return is not None:
                    swings[f"{days}d_return"] = swing_return
            results.append({
                "ticker": ticker,
                "pattern": pattern_type,
                "confidence": confidence,
                "start": start,
                "end": end,
                "score": score,
                **swings
            })
        return results
    except Exception as e:
        print(f"[!] {ticker} error in scan: {e}")
        return []

def main():
    all_results = []
    skipped_tickers = []
    errored_tickers = []

    for ticker in TICKERS:
        try:
            results = scan_ticker(ticker)
            if results:
                all_results.extend(results)
            else:
                skipped_tickers.append(ticker)
        except Exception as e:
            errored_tickers.append((ticker, str(e)))

    if all_results:
        df = pd.DataFrame(all_results)
        out_path = os.path.join(DATA_DIR, "historical_pattern_analysis.csv")
        os.makedirs(DATA_DIR, exist_ok=True)
        df.to_csv(out_path, index=False)
        print(f"[✔] Historical pattern analysis written to: {out_path}")
    else:
        print("[!] No results written.")

    if skipped_tickers:
        print(f"[ℹ] No patterns found for: {', '.join(skipped_tickers)}")

    if errored_tickers:
        print("[✘] Errors occurred for:")
        for ticker, msg in errored_tickers:
            print(f"    - {ticker}: {msg}")


if __name__ == "__main__":
    main()

#    all_results = []
#    for ticker in TICKERS:
#        all_results.extend(scan_ticker(ticker))

#    if all_results:
#        df = pd.DataFrame(all_results)
#        out_path = os.path.join(DATA_DIR, "historical_pattern_analysis.csv")
#        os.makedirs(DATA_DIR, exist_ok=True)
#        df.to_csv(out_path, index=False)
#        print(f"[✔] Historical pattern analysis written to: {out_path}")
#    else:
#        print("[!] No results written.")
