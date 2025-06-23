import logging
import os
import yaml
from stonkslib.indicators.macd import calculate_macd
from stonkslib.indicators.rsi import calculate_rsi
from stonkslib.indicators.obv import calculate_obv
from stonkslib.indicators.bollinger import calculate_bollinger_bands

# Set up logging for alerts
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Path to the tickers.yaml file
TICKER_YAML = os.path.join(os.path.dirname(__file__), "..", "data_collection", "tickers.yaml")

def load_tickers(path=TICKER_YAML):
    """Load tickers from the YAML file (stocks, crypto, ETFs)"""
    with open(path, "r") as f:
        tickers_config = yaml.safe_load(f)
    return tickers_config["stocks"] + tickers_config["crypto"] + tickers_config["etfs"]

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
    """Analyze the indicators and trigger alerts if necessary"""
    macd_score = score_macd(df)
    rsi_score = score_rsi(df)
    obv_score = score_obv(df)
    bollinger_score = score_bollinger(df)
    
    # Combine all scores to determine final action
    total_score = macd_score + rsi_score + obv_score + bollinger_score
    
    # Trigger alert based on the score
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

def trigger_alerts(message):
    """Triggers an alert by logging the message (can be extended to email/SMS)"""
    logging.info(f"ALERT: {message}")

def main():
    """Main function to run the analysis on all tickers"""
    tickers = load_tickers()  # Load all tickers (stocks, crypto, ETFs)
    
    # Example: loop through each ticker, load its data, and analyze
    for ticker in tickers:
        df = load_ticker_data(ticker)  # Assuming this function is defined elsewhere
        analyze_ticker(ticker, df)  # Analyze the ticker and trigger alerts

if __name__ == "__main__":
    main()
