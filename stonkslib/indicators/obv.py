# stonkslib/indicators/obv.py

import logging
import pandas as pd
import numpy as np
import warnings

# Suppress specific date warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def obv(df):
    """
    Calculate On-Balance Volume (OBV) for a given DataFrame.
    Returns a DataFrame with a single 'OBV' column.
    """
    df = df.copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")
    df = df.dropna(subset=["Close", "Volume"])

    direction = np.sign(df["Close"].diff()).fillna(0)
    obv_series = (direction * df["Volume"]).cumsum()
    return pd.DataFrame({"OBV": obv_series}, index=df.index)

def generate_obv_signals(df):
    """
    Generate OBV signal alerts (rising/falling).
    Returns a filtered DataFrame with Close and Signal columns.
    """
    signals = []
    for i in range(1, len(df)):
        prev = df["OBV"].iloc[i - 1]
        curr = df["OBV"].iloc[i]
        if curr > prev:
            signal = "📈 Rising OBV"
        elif curr < prev:
            signal = "📉 Falling OBV"
        else:
            signal = ""
        signals.append(signal)

        if signal:
            logging.info(f"[{df.index[i]}] {signal} — OBV: {curr:.2f}")

    df_signals = df.iloc[1:].copy()
    df_signals["Signal"] = signals
    return df_signals[df_signals["Signal"] != ""]

# === Manual test ===
if __name__ == "__main__":
    from stonkslib.utils.load_td import load_td
    from stonkslib.analysis.signals import save_csv

    ticker = "AAPL"
    interval = "1d"
    df = load_td([ticker], interval)[ticker]
    obv_df = obv(df)

    obv_df = obv_df.dropna(subset=["OBV"])
    if obv_df.empty or len(obv_df) < 2:
        print(f"[!] Not enough data to compute OBV for {ticker} ({interval})")
    else:
        signals_df = generate_obv_signals(obv_df)
        if not signals_df.empty:
            signals_out = signals_df[["Signal"]].copy()
            signals_out["obv_Close"] = df["Close"]
            signals_out = signals_out[["obv_Close", "Signal"]].rename(columns={"Signal": "obv_Signal"})
            print(signals_out.tail(5))
            save_csv(signals_out, ticker, interval, "obv_signals")
        else:
            print("\nℹ️ No recent OBV signals.")
