import logging
import os
import yaml
from stonkslib.indicators.bollinger import bollinger_bands
from stonkslib.indicators.macd import macd
from stonkslib.indicators.rsi import rsi
from stonkslib.indicators.obv import obv
from stonkslib.patterns.doubles import find_doubles
from stonkslib.patterns.head_shoulders import find_head_shoulders
from stonkslib.patterns.triangles import find_triangles
from stonkslib.patterns.wedges import find_wedges
from stonkslib.utils.load_td import load_td

# Set up logging for alerts
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(console_handler)

# Path to the tickers.yaml file
TICKER_YAML = os.path.join(os.path.dirname(__file__), "..", "..", "tickers.yaml")  # Relative path

def load_tickers(path=TICKER_YAML):
    """Load tickers from the YAML file (stocks, crypto, ETFs)"""
    with open(path, "r") as f:
        tickers_config = yaml.safe_load(f)
    tickers = tickers_config["stocks"] + tickers_config["crypto"] + tickers_config["etfs"]
    logging.info(f"Loaded tickers: {tickers}")
    return tickers

def score_macd(df):
    """Score MACD indicator to generate a signal"""
    if df["MACD"].iloc[-1] > df["Signal_Line"].iloc[-1]:
        return 20  # Buy signal
    elif df["MACD"].iloc[-1] < df["Signal_Line"].iloc[-1]:
        return -20  # Sell signal
    else:
        return 0  # Neutral signal

def score_rsi(df):
    """Score RSI indicator to generate a signal"""
    if df["RSI"].iloc[-1] > 70:
        return -20  # Sell signal (overbought)
    elif df["RSI"].iloc[-1] < 30:
        return 20  # Buy signal (oversold)
    else:
        return 0  # Neutral signal

def score_obv(df):
    """Score OBV indicator to generate a signal"""
    if df["OBV"].iloc[-1] > df["OBV"].iloc[-2]:
        return 20  # Buy signal (rising OBV)
    elif df["OBV"].iloc[-1] < df["OBV"].iloc[-2]:
        return -20  # Sell signal (falling OBV)
    else:
        return 0  # Neutral signal

def score_bollinger(df):
    """Score Bollinger Bands to generate a signal"""
    if df["Close"].iloc[-1] > df["Upper_Band"].iloc[-1]:
        return -20  # Sell signal (price above upper band)
    elif df["Close"].iloc[-1] < df["Lower_Band"].iloc[-1]:
        return 20  # Buy signal (price below lower band)
    else:
        return 0  # Neutral signal

def analyze_ticker(ticker, df):
    """Analyze the indicators and patterns, and trigger alerts if necessary"""
    
    # Debug: Check columns of the dataframe
    logging.debug(f"Columns in dataframe for {ticker}: {df.columns}")

    # Indicator scores
    macd_score = score_macd(df)
    rsi_score = score_rsi(df)
    obv_score = score_obv(df)
    bollinger_score = score_bollinger(df)
    
    # Pattern scores
    double_patterns = find_doubles(ticker, df)  # Use the pattern functions
    head_shoulders = find_head_shoulders(ticker, df)
    triangle_patterns = find_triangles(ticker, df)
    wedge_patterns = find_wedges(ticker, df)

    # Combine all scores
    total_score = macd_score + rsi_score + obv_score + bollinger_score
    total_score += len(double_patterns) * 10  # Example: reward patterns
    total_score += len(head_shoulders) * 10
    total_score += len(triangle_patterns) * 10
    total_score += len(wedge_patterns) * 10

    # Trigger alerts based on the combined score
    if total_score >= 40:
        trigger_alerts(f"Strong Buy Signal for {ticker}")
    elif total_score <= -40:
        trigger_alerts(f"Strong Sell Signal for {ticker}")
    elif total_score > 20:
        trigger_alerts(f"Moderate Buy Signal for {ticker}")
    elif total_score < -20:
        trigger_alerts(f"Moderate Sell Signal for {ticker}")
    else:
        trigger_alerts(f"No significant action for {ticker}")

    # Log the detected patterns for verification
    logging.info(f"Patterns detected for {ticker}:")
    logging.info(f"Doubles: {double_patterns}")
    logging.info(f"Head & Shoulders: {head_shoulders}")
    logging.info(f"Triangles: {triangle_patterns}")
    logging.info(f"Wedges: {wedge_patterns}")

def trigger_alerts(message):
    """Triggers an alert by logging the message (can be extended to email/SMS)"""
    logging.info(f"ALERT: {message}")

def main():
    """Main function to run the analysis on all tickers"""
    tickers = load_tickers()  # Load all tickers (stocks, crypto, ETFs)
    
    # Example: loop through each ticker, load its data, and analyze
    for ticker in tickers:
        logging.info(f"Analyzing {ticker}...")
        df = load_td(ticker, interval="1d", lookback=60)  # Load ticker data (interval can be passed)
        analyze_ticker(ticker, df)  # Analyze the ticker and trigger alerts

if __name__ == "__main__":
    main()
