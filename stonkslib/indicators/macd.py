# stonkslib/indicators/macd.py

import pandas as pd
import logging
import warnings
from stonkslib.utils.load_td import load_td

# Suppress specific warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# More Sensitive - Faster reaction to price changes (short-term trades)
#def macd(df, short_window=6, long_window=13, signal_window=5)

# More Strict MACD - Slower, smoother signals (long-term trades)
#def macd(df, short_window=19, long_window=39, signal_window=10)

def macd(df, short_window=12, long_window=26, signal_window=9):
    """
    Calculate MACD and Signal Line for a given DataFrame.
    """
    if "Close" not in df.columns:
        raise ValueError("DataFrame must contain a 'Close' column.")

    ema_short = df["Close"].ewm(span=short_window, adjust=False).mean()
    ema_long = df["Close"].ewm(span=long_window, adjust=False).mean()

    df["MACD"] = ema_short - ema_long
    df["Signal_Line"] = df["MACD"].ewm(span=signal_window, adjust=False).mean()

    return df

def generate_macd_signals(df):
    """
    Generate MACD crossover signals.
    """
    signals = []

    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        if curr["MACD"] > curr["Signal_Line"] and prev["MACD"] <= prev["Signal_Line"]:
            signals.append("📈 Bullish Crossover")
        elif curr["MACD"] < curr["Signal_Line"] and prev["MACD"] >= prev["Signal_Line"]:
            signals.append("📉 Bearish Crossover")
        else:
            signals.append("")

    df = df.iloc[1:].copy()
    df["Signal"] = signals
    return df[df["Signal"] != ""]

# Test entrypoint
if __name__ == "__main__":
    ticker = "AAPL"
    interval = "1d"

    df_dict = load_td([ticker], interval)
    df = df_dict[ticker]

    df = macd(df)

    df = df.dropna(subset=["MACD", "Signal_Line", "Close"])
    if df.empty:
        print(f"[!] Not enough data to compute MACD for {ticker} ({interval})")
    else:
        latest = df.iloc[-1]
        direction = "🔼" if latest["MACD"] > latest["Signal_Line"] else (
                    "🔽" if latest["MACD"] < latest["Signal_Line"] else "➡️")

        print(df.tail(10)[["Close", "MACD", "Signal_Line"]])
        print(f"\n{direction} Latest MACD: {latest['MACD']:.2f} vs Signal: {latest['Signal_Line']:.2f}")

        recent_signals = generate_macd_signals(df.tail(20))
        if not recent_signals.empty:
            print("\nRecent Signals:")
            print(recent_signals[["MACD", "Signal_Line", "Signal"]].tail(5))
