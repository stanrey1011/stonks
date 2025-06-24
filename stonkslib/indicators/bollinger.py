# stonkslib/indicators/bollinger.py

import logging
import pandas as pd
import warnings

# Suppress date format warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def bollinger_bands(df, window=20, num_std_dev=2):
    """
    Calculate Bollinger Bands for a given DataFrame (expects 'Close' column).
    Returns a new DataFrame with columns: 'MA', 'STD', 'Upper_Band', 'Lower_Band'.
    """
    result = pd.DataFrame(index=df.index)
    result["MA"] = df["Close"].rolling(window=window).mean()
    result["STD"] = df["Close"].rolling(window=window).std()
    result["Upper_Band"] = result["MA"] + (num_std_dev * result["STD"])
    result["Lower_Band"] = result["MA"] - (num_std_dev * result["STD"])
    result["Close"] = df["Close"]
    return result

def generate_bollinger_signals(df):
    """
    Add breakout signal column and log detections.
    Returns a DataFrame with non-empty signals only.
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

    df_signals = df.iloc[1:].copy()
    df_signals["Signal"] = signals
    return df_signals[df_signals["Signal"] != ""]

# 🔬 Manual test
if __name__ == "__main__":
    from stonkslib.utils.load_td import load_td
    ticker = "AAPL"
    interval = "1d"
    df = load_td([ticker], interval)[ticker]
    bb_df = bollinger_bands(df)

    # Drop rows with missing values in indicator columns
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
