import logging
import pandas as pd
import warnings

# Suppress date format warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def moving_averages(df, swing_window=20, long_window=50, ma_type="EMA"):
    """
    Calculate swing-term and long-term moving averages.
    Returns a new DataFrame with columns: 'MA_Swing', 'MA_Long'.
    ma_type: 'EMA' or 'SMA'
    """
    result = pd.DataFrame(index=df.index)
    if ma_type.upper() == "EMA":
        result["MA_Swing"] = df["Close"].ewm(span=swing_window, adjust=False).mean()
        result["MA_Long"] = df["Close"].ewm(span=long_window, adjust=False).mean()
    else:
        result["MA_Swing"] = df["Close"].rolling(window=swing_window).mean()
        result["MA_Long"] = df["Close"].rolling(window=long_window).mean()
    result["Close"] = df["Close"]
    return result

def generate_ma_signals(df, ticker=None, interval=None):
    """
    Generate signals for MA crossovers.
    Returns a DataFrame with non-empty signals only.
    Adds ticker and interval to logging.
    """
    signals = []

    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        signal = ""

        # Bullish crossover: swing MA crosses above long MA
        if prev["MA_Swing"] <= prev["MA_Long"] and curr["MA_Swing"] > curr["MA_Long"]:
            signal = "🟢 Bullish MA Crossover"
        # Bearish crossover: swing MA crosses below long MA
        elif prev["MA_Swing"] >= prev["MA_Long"] and curr["MA_Swing"] < curr["MA_Long"]:
            signal = "🔴 Bearish MA Crossover"

        signals.append(signal)

        if signal:
            log_prefix = f"[{ticker} {interval}]" if ticker and interval else ""
            logging.info(f"{log_prefix} [{curr.name}] {signal} — Close: {curr['Close']:.2f}")

    df_signals = df.iloc[1:].copy()
    df_signals["Signal"] = signals
    return df_signals[df_signals["Signal"] != ""]

# 🔬 Manual test
if __name__ == "__main__":
    from stonkslib.utils.load_td import load_td
    ticker = "AAPL"
    interval = "1d"
    df = load_td([ticker], interval)[ticker]
    ma_df = moving_averages(df, swing_window=20, long_window=50, ma_type="EMA")

    ma_df = ma_df.dropna(subset=["MA_Swing", "MA_Long", "Close"])

    if ma_df.empty:
        print(f"[!] Not enough data to compute Moving Averages for {ticker} ({interval})")
    else:
        signals_df = generate_ma_signals(ma_df, ticker=ticker, interval=interval)
        latest = ma_df.iloc[-1]
        ma_relation = (
            "🔼 Above" if latest["MA_Swing"] > latest["MA_Long"]
            else "🔽 Below" if latest["MA_Swing"] < latest["MA_Long"]
            else "➡️ Equal"
        )

        print(ma_df.tail(10)[["Close", "MA_Swing", "MA_Long"]])
        print(f"\n{ma_relation} — Latest Swing MA: {latest['MA_Swing']:.2f}, "
              f"Long MA: {latest['MA_Long']:.2f}, Close: {latest['Close']:.2f}")

        if not signals_df.empty:
            print("\n📣 Recent MA Crossover Signals:")
            print(signals_df[["Close", "Signal"]].tail(5))
        else:
            print("\nℹ️ No recent MA crossover signals.")
