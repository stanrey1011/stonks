# stonkslib/indicators/macd.py

import pandas as pd
import logging
import warnings

# Suppress specific warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def macd(df, short_window=12, long_window=26, signal_window=9):
    """
    Calculate MACD and Signal Line for a given DataFrame (expects 'Close' column).
    Returns a DataFrame with columns: 'MACD', 'Signal_Line'.
    """
    if "Close" not in df.columns:
        raise ValueError("DataFrame must contain a 'Close' column.")

    macd_out = pd.DataFrame(index=df.index)
    ema_short = df["Close"].ewm(span=short_window, adjust=False).mean()
    ema_long = df["Close"].ewm(span=long_window, adjust=False).mean()

    macd_out["MACD"] = ema_short - ema_long
    macd_out["Signal_Line"] = macd_out["MACD"].ewm(span=signal_window, adjust=False).mean()
    return macd_out

def generate_macd_signals(df):
    """
    Generate MACD crossover signals.
    Returns DataFrame with non-empty signals only.
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

    df_signals = df.iloc[1:].copy()
    df_signals["Signal"] = signals
    return df_signals[df_signals["Signal"] != ""]

# Manual test entrypoint
if __name__ == "__main__":
    from stonkslib.utils.load_td import load_td
    ticker = "AAPL"
    interval = "1d"

    df = load_td([ticker], interval)[ticker]
    macd_df = macd(df)

    macd_df = macd_df.dropna(subset=["MACD", "Signal_Line"])
    if macd_df.empty:
        print(f"[!] Not enough data to compute MACD for {ticker} ({interval})")
    else:
        latest = macd_df.iloc[-1]
        direction = "🔼" if latest["MACD"] > latest["Signal_Line"] else (
                    "🔽" if latest["MACD"] < latest["Signal_Line"] else "➡️")

        print(macd_df.tail(10)[["MACD", "Signal_Line"]])
        print(f"\n{direction} Latest MACD: {latest['MACD']:.2f} vs Signal: {latest['Signal_Line']:.2f}")

        recent_signals = generate_macd_signals(macd_df.tail(20))
        if not recent_signals.empty:
            print("\nRecent Signals:")
            print(recent_signals[["MACD", "Signal_Line", "Signal"]].tail(5))
