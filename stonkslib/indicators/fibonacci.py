import logging
import pandas as pd
import warnings

# Suppress specific warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def calculate_fibonacci_levels(df, lookback=100, direction="auto"):
    """
    Calculate Fibonacci retracement and extension levels based on a recent swing.

    Returns a dictionary with retracements, extensions, and the swing range.
    """
    if df.empty or len(df) < lookback:
        return {}

    recent_data = df[-lookback:]
    high = recent_data['Close'].max()
    low = recent_data['Close'].min()

    if direction == "auto":
        direction = "uptrend" if df['Close'].iloc[-1] > recent_data['Close'].mean() else "downtrend"

    if direction == "uptrend":
        swing_low = low
        swing_high = high
    else:
        swing_low = high
        swing_high = low

    diff = swing_high - swing_low

    retracements = {
        0.236: swing_high - 0.236 * diff,
        0.382: swing_high - 0.382 * diff,
        0.500: swing_high - 0.500 * diff,
        0.618: swing_high - 0.618 * diff,
        0.786: swing_high - 0.786 * diff,
    }

    extensions = {
        1.272: swing_high + 0.272 * diff,
        1.618: swing_high + 0.618 * diff,
        2.618: swing_high + 1.618 * diff,
    }

    return {
        "retracements": retracements,
        "extensions": extensions,
        "swing": {"low": swing_low, "high": swing_high, "direction": direction}
    }


def generate_fibonacci_signals(df, fib_levels, ticker=None, interval=None):
    """
    Generate signals based on price interaction with Fibonacci levels.
    """
    signals = []
    for i in range(1, len(df)):
        price = df.iloc[i]['Close']
        signal = ""

        for level, retrace_price in fib_levels['retracements'].items():
            if abs(price - retrace_price) / retrace_price < 0.01:
                signal = f"🟡 Near {int(level * 100)}% Retracement"
                break

        for level, ext_price in fib_levels['extensions'].items():
            if abs(price - ext_price) / ext_price < 0.01:
                signal = f"🟢 Near {int(level * 100)}% Extension"
                break

        signals.append(signal)

        if signal:
            log_prefix = f"[{ticker} {interval}]" if ticker and interval else ""
            logging.info(f"{log_prefix} [{df.index[i]}] {signal} — Close: {price:.2f}")

    df_signals = df.iloc[1:].copy()
    df_signals["Signal"] = signals
    return df_signals[df_signals["Signal"] != ""]


# 🔬 Manual test
if __name__ == "__main__":
    from stonkslib.utils.load_td import load_td
    ticker = "AAPL"
    interval = "1d"
    df = load_td([ticker], interval)[ticker]

    fib_data = calculate_fibonacci_levels(df, lookback=100)
    if not fib_data:
        print(f"[!] Not enough data to compute Fibonacci levels for {ticker} ({interval})")
    else:
        print("\n🔢 Fibonacci Levels:")
        print("Retracements:", fib_data['retracements'])
        print("Extensions:", fib_data['extensions'])
        
        fib_signals = generate_fibonacci_signals(df, fib_data, ticker=ticker, interval=interval)

        if not fib_signals.empty:
            print("\n📣 Recent Fibonacci Signals:")
            print(fib_signals[["Close", "Signal"]].tail(5))
        else:
            print("\nℹ️ No recent Fibonacci interaction signals.")
