import os
import pandas as pd
import logging
import warnings
import yaml

from stonkslib.utils.load_td import load_td
from stonkslib.indicators.bollinger import bollinger_bands
from stonkslib.indicators.macd import macd
from stonkslib.indicators.obv import obv
from stonkslib.indicators.rsi import rsi

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Suppress specific warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# ---- Indicator scoring functions ----
def score_macd(df):
    if "MACD" not in df.columns or "Signal_Line" not in df.columns:
        df = macd(df)
    if "MACD" in df.columns and "Signal_Line" in df.columns:
        return int(df["MACD"].iloc[-1] > df["Signal_Line"].iloc[-1])
    return 0

def score_rsi(df, interval, lower=30, upper=70):
    if "RSI" not in df.columns:
        df = rsi(df, interval)
    if "RSI" in df.columns:
        rsi_val = df["RSI"].iloc[-1]
        return int(rsi_val < lower or rsi_val > upper)
    return 0

def score_obv(df):
    if "OBV" not in df.columns:
        df = obv(df)
    return 1 if "OBV" in df.columns else 0

def score_bollinger(df):
    if "Upper_Band" not in df.columns or "Lower_Band" not in df.columns:
        df = bollinger_bands(df)
    if "Upper_Band" in df.columns and "Lower_Band" in df.columns:
        close = df["Close"].iloc[-1]
        return int(close > df["Upper_Band"].iloc[-1] or close < df["Lower_Band"].iloc[-1])
    return 0

# ---- Ticker loader ----
def load_tickers():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(script_dir, "../../"))
    ticker_path = os.path.join(root_dir, "tickers.yaml")

    with open(ticker_path, "r") as f:
        tickers_config = yaml.safe_load(f)

    all_tickers = []
    for category in tickers_config:
        all_tickers.extend(tickers_config[category])

    logger.info(f"Loaded tickers: {all_tickers}")
    return all_tickers

# ---- Analysis driver ----
def analyze_ticker(ticker, df, interval):
    macd_score = score_macd(df)
    rsi_score = score_rsi(df, interval)
    obv_score = score_obv(df)
    boll_score = score_bollinger(df)

    total = macd_score + rsi_score + obv_score + boll_score
    logger.info(f"{ticker} Score: {total} (MACD={macd_score}, RSI={rsi_score}, OBV={obv_score}, BB={boll_score})")

    if total >= 3:
        logger.info(f"🚨 Alert: {ticker} shows strong signal!")

# ---- Main entry ----
def main():
    tickers = load_tickers()
    interval = "1d"
    lookback = 60

    for ticker in tickers:
        logger.info(f"Analyzing {ticker}...")
        df = load_td(ticker, interval, lookback)
        if df is not None:
            analyze_ticker(ticker, df, interval)
        else:
            logger.warning(f"⚠️ No data for {ticker}")

if __name__ == "__main__":
    main()
