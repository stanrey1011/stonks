import os
import yaml
from project.indicators.macd import calculate_macd
from project.indicators.rsi import calculate_rsi
from project.indicators.obv import calculate_obv
from project.indicators.bollinger import calculate_bollinger_bands

TICKER_YAML = os.path.join(os.path.dirname(__file__), "..", "data_collection", "tickers.yaml")

def load_tickers(path=TICKER_YAML):
    with open(path, "r") as f:
        tickers_config = yaml.safe_load(f)
    return tickers_config["stocks"] + tickers_config["crypto"] + tickers_config["etfs"]

def score_macd(df):
    if df["MACD"].iloc[-1] > df["Signal_Line"].iloc[-1]:
        return 20
    elif df["MACD"].iloc[-1] < df["Signal_Line"].iloc[-1]:
        return -20
    return 0

def score_rsi(df):
    rsi = df["RSI"].iloc[-1]
    if rsi < 30:
        return 15
    elif rsi > 70:
        return -15
    return 0

def score_obv(df):
    price_diff = df["Close"].diff().iloc[-1]
    obv_diff = df["OBV"].diff().iloc[-1]
    if price_diff > 0 and obv_diff > 0:
        return 15
    elif price_diff > 0 and obv_diff < 0:
        return -15
    return 0

def score_bollinger(df):
    close = df["Close"].iloc[-1]
    upper = df["Upper_Band"].iloc[-1]
    lower = df["Lower_Band"].iloc[-1]
    if close < lower:
        return +10
    elif close > upper:
        return -10
    return 0

def analyze_ticker(ticker):
    try:
        macd_df = calculate_macd(ticker)
        rsi_df = calculate_rsi(ticker)
        obv_df = calculate_obv(ticker)
        bb_df = calculate_bollinger_bands(ticker)

        # Merge all latest values into one row (assumes same length)
        score = 0
        score += score_macd(macd_df)
        score += score_rsi(rsi_df)
        score += score_obv(obv_df)
        score += score_bollinger(bb_df)

        if score >= 30:
            signal = "BUY"
        elif score <= -30:
            signal = "SELL"
        else:
            signal = "HOLD"

        print(f"[{ticker}] Score: {score:>3} → Signal: {signal}")
    except Exception as e:
        print(f"[!] Failed to analyze {ticker}: {e}")

def main():
    tickers = load_tickers()
    print("\n📈 Trade Alerts\n" + "-"*40)
    for ticker in tickers:
        analyze_ticker(ticker)

if __name__ == "__main__":
    main()
