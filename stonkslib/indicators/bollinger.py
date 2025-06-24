# stonkslib/indicators/bollinger.py

import logging
import pandas as pd
from stonkslib.utils.load_td import load_td
import warnings

# Suppress date format warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# More sensitive - tighter bands and frequent
#bb_df = bollinger_bands("AAPL", "1d", window=10, num_std_dev=1.5)

# More strict - wider bands and less frequent
#bb_df = bollinger_bands("AAPL", "1d", window=30, num_std_dev=2.5)

def bollinger_bands(ticker, interval, window=20, num_std_dev=2):
    """
    Calculate Bollinger Bands for a given ticker using clean data.
    """
    df_dict = load_td([ticker], interval)
    df = df_dict[ticker]

    df["MA"] = df["Close"].rolling(window=window).mean()
    df["STD"] = df["Close"].rolling(window=window).std()
    df["Upper_Band"] = df["MA"] + (num_std_dev * df["STD"])
    df["Lower_Band"] = df["MA"] - (num_std_dev * df["STD"])

    return df

def generate_bollinger_signals(df):
    """
    Add breakout signal column and log detections.
    """
    signals = []

    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        signal = ""

        if curr["Close"] > curr["Upper_Band"] and prev["Close"] <= prev["Upper_Band"]:
            signal = "📈 Breakout Above"
        elif curr["Close"] < curr["Lower_Band"] and prev["Close"] >= prev["Lower_Band"]:
            signal = "📉 Breakout Below"

        signals.append(signal)

        if signal:
            logging.info(f"[{curr.name}] {signal} — Close: {curr['Close']:.2f}")

    df = df.iloc[1:].copy()
    df["Signal"] = signals
    return df[df["Signal"] != ""]

# 🔬 Manual test
if __name__ == "__main__":
    ticker = "AAPL"
    interval = "1d"
    bb_df = bollinger_bands(ticker, interval)

    # Drop rows with any missing values in the indicator columns
    bb_df = bb_df.dropna(subset=["Upper_Band", "Lower_Band", "MA", "Close"])

    if bb_df.empty:
        print(f"[!] Not enough data to compute Bollinger Bands for {ticker} ({interval})")
    else:
        signals_df = generate_bollinger_signals(bb_df)

        latest = bb_df.iloc[-1]
        direction = "🔼" if latest["Close"] > latest["Upper_Band"] else (
                    "🔽" if latest["Close"] < latest["Lower_Band"] else "➡️")

        print(bb_df.tail(10)[["Close", "MA", "Upper_Band", "Lower_Band"]])
        print(f"\n{direction} Latest Close: {latest['Close']:.2f} vs Bands "
              f"({latest['Lower_Band']:.2f} - {latest['Upper_Band']:.2f})")

        if not signals_df.empty:
            print("\n📣 Recent Signals:")
            print(signals_df[["Close", "Signal"]].tail(5))
        else:
            print("\nℹ️ No recent Bollinger breakout signals.")
