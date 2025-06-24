# stonkslib/alerts/trade_alerts.py

import logging
import warnings
import yaml
import os

from stonkslib.indicators.bollinger import bollinger_bands, generate_bollinger_signals
from stonkslib.indicators.macd import macd
from stonkslib.indicators.obv import obv
from stonkslib.indicators.rsi import rsi

from stonkslib.patterns.doubles import find_doubles
from stonkslib.patterns.triangles import find_triangles
from stonkslib.patterns.wedges import find_wedges
from stonkslib.patterns.head_shoulders import find_head_shoulders

from stonkslib.utils.load_td import load_td

warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TICKER_YAML = os.path.join(BASE_DIR, "..", "tickers.yaml")

def load_ticker_list(yaml_file=TICKER_YAML):
    with open(yaml_file, "r") as f:
        tickers = yaml.safe_load(f)
    result = []
    for category in tickers:
        result.extend(tickers[category])
    return result

def aggregate_alerts(ticker, interval):
    """Aggregate all indicator and pattern signals for a single ticker/interval."""
    alerts = []

    # --- Indicators ---
    # Bollinger Bands
    try:
        bb_df = bollinger_bands(ticker, interval)
        bb_signals = generate_bollinger_signals(bb_df)
        for idx, row in bb_signals.iterrows():
            alerts.append(f"{ticker} ({interval}) BB {row['Signal']} at {idx}")
    except Exception as e:
        logging.info(f"Bollinger error for {ticker} ({interval}): {e}")

    # MACD
    try:
        df = load_td([ticker], interval)[ticker]
        macd_df = macd(df)
        macd_alerts = macd_signals(macd_df)
        for alert in macd_alerts:
            alerts.append(f"{ticker} ({interval}) MACD {alert}")
    except Exception as e:
        logging.info(f"MACD error for {ticker} ({interval}): {e}")

    # OBV
    try:
        obv_df = obv(ticker, interval)
        obv_alerts = obv_signals(obv_df)
        for alert in obv_alerts:
            alerts.append(f"{ticker} ({interval}) OBV {alert}")
    except Exception as e:
        logging.info(f"OBV error for {ticker} ({interval}): {e}")

    # RSI
    try:
        rsi_df = rsi(ticker, interval)
        rsi_alerts = rsi_signals(rsi_df)
        for alert in rsi_alerts:
            alerts.append(f"{ticker} ({interval}) RSI {alert}")
    except Exception as e:
        logging.info(f"RSI error for {ticker} ({interval}): {e}")

    # --- Patterns ---
    try:
        doubles = find_doubles(ticker, interval)
        for start, end, pattern, confidence in doubles:
            direction = "⬇️" if "Bottom" in pattern else "⬆️"
            alerts.append(f"{ticker} ({interval}) {direction} {pattern} from {start} to {end}, confidence={confidence}")
    except Exception as e:
        logging.info(f"Doubles error for {ticker} ({interval}): {e}")

    try:
        triangles = find_triangles(ticker, interval)
        for start, end, pattern, confidence in triangles:
            emoji = "🔺" if "Ascending" in pattern else "🔻" if "Descending" in pattern else "🔼"
            alerts.append(f"{ticker} ({interval}) {emoji} {pattern} from {start} to {end}, confidence={confidence}")
    except Exception as e:
        logging.info(f"Triangles error for {ticker} ({interval}): {e}")

    try:
        wedges = find_wedges(ticker, interval)
        for start, end, pattern, confidence in wedges:
            emoji = "📉" if "Falling" in pattern else "📈"
            alerts.append(f"{ticker} ({interval}) {emoji} {pattern} from {start} to {end}, confidence={confidence}")
    except Exception as e:
        logging.info(f"Wedges error for {ticker} ({interval}): {e}")

    try:
        hs = find_head_shoulders(ticker, interval)
        for left, head, right, pattern, confidence in hs:
            alerts.append(f"{ticker} ({interval}) 🤕 {pattern} from {left} to {right}, confidence={confidence}")
    except Exception as e:
        logging.info(f"Head-Shoulders error for {ticker} ({interval}): {e}")

    return alerts

def main(intervals=["1d", "1h", "15m", "1wk"]):
    tickers = load_ticker_list()
    for ticker in tickers:
        print(f"\n=== {ticker} ===")
        for interval in intervals:
            alerts = aggregate_alerts(ticker, interval)
            if alerts:
                for alert in alerts:
                    print(alert)
            else:
                print(f"{ticker} ({interval}): No signals found.")

if __name__ == "__main__":
    main()
