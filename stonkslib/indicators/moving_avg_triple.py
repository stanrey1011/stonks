import logging
import pandas as pd
import warnings

# Suppress date format warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def moving_averages_triple(df, short_window=9, medium_window=21, long_window=50, ma_type="EMA"):
    """
    Calculate triple moving averages for trend filtering and signals.
    Returns a DataFrame with 'MA_Short', 'MA_Medium', 'MA_Long'.
    ma_type: 'EMA' or 'SMA'
    """
    result = pd.DataFrame(index=df.index)
    if ma_type.upper() == "EMA":
        result["MA_Short"] = df["Close"].ewm(span=short_window, adjust=False).mean()
        result["MA_Medium"] = df["Close"].ewm(span=medium_window, adjust=False).mean()
        result["MA_Long"] = df["Close"].ewm(span=long_window, adjust=False).mean()
    else:
        result["MA_Short"] = df["Close"].rolling(window=short_window).mean()
        result["MA_Medium"] = df["Close"].rolling(window=medium_window).mean()
        result["MA_Long"] = df["Close"].rolling(window=long_window).mean()
    result["Close"] = df["Close"]
    return result

def generate_triple_ma_signals(df, ticker=None, interval=None):
    """
    Generate signals when all three MAs are in bullish or bearish alignment.
    Returns a DataFrame with non-empty signals only.
    Adds ticker and interval to logging.
    """
    signals = []

    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        signal = ""

        # Bullish: Short > Medium > Long, and a new alignment/crossover just happened
        if (prev["MA_Short"] <= prev["MA_Medium"] or prev["MA_Medium"] <= prev["MA_Long"]) \
           and (curr["MA_Short"] > curr["MA_Medium"] > curr["MA_Long"]):
            signal = "🟢 Triple MA Bullish Alignment"

        # Bearish: Short < Medium < Long, and a new alignment/crossover just happened
        elif (prev["MA_Short"] >= prev["MA_Medium"] or prev["MA_Medium"] >= prev["MA_Long"]) \
             and (curr["MA_Short"] < curr["MA_Medium"] < curr["MA_Long"]):
            signal = "🔴 Triple MA Bearish Alignment"

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
    triple_ma_df = moving_averages_triple(df, short_window=9, medium_window=21, long_window=50, ma_type="EMA")

    triple_ma_df = triple_ma_df.dropna(subset=["MA_Short", "MA_Medium", "MA_Long", "Close"])

    if triple_ma_df.empty:
        print(f"[!] Not enough data to compute Triple MA for {ticker} ({interval})")
    else:
        signals_df = generate_triple_ma_signals(triple_ma_df, ticker=ticker, interval=interval)
        latest = triple_ma_df.iloc[-1]
        if latest["MA_Short"] > latest["MA_Medium"] > latest["MA_Long"]:
            relation = "🔼 Bullish Alignment"
        elif latest["MA_Short"] < latest["MA_Medium"] < latest["MA_Long"]:
            relation = "🔽 Bearish Alignment"
        else:
            relation = "➡️ Mixed"

        print(triple_ma_df.tail(10)[["Close", "MA_Short", "MA_Medium", "MA_Long"]])
        print(f"\n{relation} — Short: {latest['MA_Short']:.2f}, "
              f"Medium: {latest['MA_Medium']:.2f}, Long: {latest['MA_Long']:.2f}, Close: {latest['Close']:.2f}")

        if not signals_df.empty:
            print("\n📣 Recent Triple MA Alignment Signals:")
            print(signals_df[["Close", "Signal"]].tail(5))
        else:
            print("\nℹ️ No recent triple MA alignment signals.")
