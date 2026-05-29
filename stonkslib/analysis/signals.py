import logging
import warnings
import yaml
import os
import pandas as pd

from stonkslib.indicators.bollinger import bollinger_bands, generate_bollinger_signals
from stonkslib.indicators.macd import macd, generate_macd_signals
from stonkslib.indicators.obv import obv, generate_obv_signals
from stonkslib.indicators.rsi import rsi, generate_rsi_signals
from stonkslib.indicators.moving_avg_double import moving_averages, generate_ma_signals
from stonkslib.indicators.moving_avg_triple import moving_averages_triple, generate_triple_ma_signals
from stonkslib.indicators.fibonacci import calculate_fibonacci_levels, generate_fibonacci_signals

from stonkslib.patterns.doubles import find_doubles
from stonkslib.patterns.triangles import find_triangles
from stonkslib.patterns.wedges import find_wedges
from stonkslib.patterns.head_shoulders import find_head_shoulders

from stonkslib.utils.load_td import load_td

# Suppress specific warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# --- Logging setup ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
LOG_DIR = os.path.join(PROJECT_ROOT, "log")
os.makedirs(LOG_DIR, exist_ok=True)
LOGFILE = os.path.join(LOG_DIR, "build_db.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOGFILE),
        logging.StreamHandler()
    ]
)

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TICKER_YAML = os.path.join(BASE_DIR, "..", "tickers.yaml")
BASE_ANALYSIS_DIR = os.path.join(BASE_DIR, "..", "data", "analysis", "signals")

def load_ticker_list(yaml_file=TICKER_YAML):
    with open(yaml_file, "r") as f:
        tickers = yaml.safe_load(f)
    result = []
    for category in tickers:
        items = tickers[category]
        if isinstance(items, str):
            items = [items]
        result.extend(items)
    return result

def save_csv(df, ticker, interval, name):
    if df is None or df.empty:
        logging.warning(f"[!] Skipping save — empty DataFrame: {ticker} {interval} {name}")
        return
    outdir = os.path.join(BASE_ANALYSIS_DIR, ticker, interval)
    os.makedirs(outdir, exist_ok=True)
    df.to_csv(os.path.join(outdir, f"{name}.csv"))

def aggregate_and_save(ticker, interval):
    status = {}

    try:
        df = load_td([ticker], interval)[ticker]
        if "Close" not in df.columns:
            raise ValueError("Missing 'Close' column in loaded data")
    except Exception as e:
        logging.error(f"[{ticker} {interval}] Data load error: {e}")
        for key in ["rsi", "macd", "bollinger", "obv", "ma_double", "ma_triple", "fibonacci"]:
            status[key] = f"error: {e}"
        return status

    # --- RSI ---
    try:
        series = rsi(df.copy(), period=14)
        save_csv(pd.DataFrame({"RSI_14": series}), ticker, interval, "rsi_14")
        rsi_signals = generate_rsi_signals(series)
        if not rsi_signals.empty:
            save_csv(rsi_signals, ticker, interval, "rsi_14_signals")
        status["rsi"] = "ok"
    except Exception as e:
        logging.error(f"[{ticker} {interval}] RSI error: {e}")
        status["rsi"] = f"error: {e}"

    # --- MACD ---
    try:
        out = macd(df.copy(), short_window=12, long_window=26, signal_window=9)
        save_csv(pd.DataFrame({"MACD_12_26_9": out["MACD"]}, index=df.index), ticker, interval, "macd")
        sigs = generate_macd_signals(out)
        if not sigs.empty:
            save_csv(sigs, ticker, interval, "macd_signals")
        status["macd"] = "ok"
    except Exception as e:
        logging.error(f"[{ticker} {interval}] MACD error: {e}")
        status["macd"] = f"error: {e}"

    # --- Bollinger Bands ---
    try:
        bands = bollinger_bands(df.copy(), window=20, num_std_dev=2)
        bb_df = pd.DataFrame({
            "BB_upper_20_2": bands["Upper_Band"],
            "BB_lower_20_2": bands["Lower_Band"],
        }, index=df.index)
        save_csv(bb_df, ticker, interval, "bollinger")
        sigs = generate_bollinger_signals(bands)
        if not sigs.empty:
            save_csv(sigs[["Close", "Signal"]], ticker, interval, "bollinger_signals")
        status["bollinger"] = "ok"
    except Exception as e:
        logging.error(f"[{ticker} {interval}] Bollinger error: {e}")
        status["bollinger"] = f"error: {e}"

    # --- OBV ---
    try:
        obv_df = obv(df.copy())
        save_csv(obv_df, ticker, interval, "obv")
        obv_signals = generate_obv_signals(obv_df)
        if not obv_signals.empty:
            save_csv(obv_signals, ticker, interval, "obv_signals")
        status["obv"] = "ok"
    except Exception as e:
        logging.error(f"[{ticker} {interval}] OBV error: {e}")
        status["obv"] = f"error: {e}"

    # --- Double MA ---
    try:
        ma_df = moving_averages(df.copy(), swing_window=20, long_window=50, ma_type="EMA")
        ma_signals_df = generate_ma_signals(ma_df, ticker=ticker, interval=interval)
        save_csv(ma_df, ticker, interval, "ma_double")
        save_csv(ma_signals_df, ticker, interval, "ma_double_signals")
        status["ma_double"] = "ok"
    except Exception as e:
        logging.error(f"[{ticker} {interval}] Double MA error: {e}")
        status["ma_double"] = f"error: {e}"

    # --- Triple MA ---
    try:
        triple_ma_df = moving_averages_triple(df.copy(), short_window=9, medium_window=21, long_window=50, ma_type="EMA")
        triple_ma_signals_df = generate_triple_ma_signals(triple_ma_df, ticker=ticker, interval=interval)
        save_csv(triple_ma_df, ticker, interval, "ma_triple")
        save_csv(triple_ma_signals_df, ticker, interval, "ma_triple_signals")
        status["ma_triple"] = "ok"
    except Exception as e:
        logging.error(f"[{ticker} {interval}] Triple MA error: {e}")
        status["ma_triple"] = f"error: {e}"

    # --- Fibonacci ---
    try:
        fib_data = calculate_fibonacci_levels(df, lookback=100)
        if fib_data:
            raw_signals = generate_fibonacci_signals(df, fib_data, ticker=ticker, interval=interval)
            if not raw_signals.empty:
                fib_signals = raw_signals[["Close", "Signal"]].rename(
                    columns={"Close": "fibonacci_Close", "Signal": "fibonacci_Signal"}
                )
                fib_signals = fib_signals.tail(5)
                save_csv(fib_signals, ticker, interval, "fibonacci")
        status["fibonacci"] = "ok"
    except Exception as e:
        logging.error(f"[{ticker} {interval}] Fibonacci error: {e}")
        status["fibonacci"] = f"error: {e}"

    # --- Patterns ---
    try:
        doubles = find_doubles(ticker, interval)
        df_doubles = pd.DataFrame(doubles, columns=["start", "end", "pattern", "confidence"])
        save_csv(df_doubles, ticker, interval, "doubles")
        status["doubles"] = "ok"
    except Exception as e:
        logging.error(f"[{ticker} {interval}] Doubles error: {e}")
        status["doubles"] = f"error: {e}"

    try:
        triangles = find_triangles(ticker, interval)
        df_triangles = pd.DataFrame(triangles, columns=["start", "end", "pattern", "confidence"])
        save_csv(df_triangles, ticker, interval, "triangles")
        status["triangles"] = "ok"
    except Exception as e:
        logging.error(f"[{ticker} {interval}] Triangles error: {e}")
        status["triangles"] = f"error: {e}"

    try:
        wedges = find_wedges(ticker, interval)
        df_wedges = pd.DataFrame(wedges, columns=["start", "end", "pattern", "confidence"])
        save_csv(df_wedges, ticker, interval, "wedges")
        status["wedges"] = "ok"
    except Exception as e:
        logging.error(f"[{ticker} {interval}] Wedges error: {e}")
        status["wedges"] = f"error: {e}"

    try:
        hs = find_head_shoulders(ticker, interval)
        df_hs = pd.DataFrame(hs, columns=["left", "head", "right", "pattern", "confidence"])
        save_csv(df_hs, ticker, interval, "head_shoulders")
        status["head_shoulders"] = "ok"
    except Exception as e:
        logging.error(f"[{ticker} {interval}] Head-Shoulders error: {e}")
        status["head_shoulders"] = f"error: {e}"

    return status

def main(intervals=["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]):
    tickers = load_ticker_list()
    summary = {}
    for ticker in tickers:
        summary[ticker] = {}
        for interval in intervals:
            print(f"\n=== {ticker} — {interval} ===")
            status = aggregate_and_save(ticker, interval)
            summary[ticker][interval] = status
            print(f"Results: {status}")
    for ticker in summary:
        for interval in summary[ticker]:
            logging.info(f"[{ticker} {interval}] Results: {summary[ticker][interval]}")

def run_signals():
    """Used by stonks analeyes CLI command"""
    main()

if __name__ == "__main__":
    main()
