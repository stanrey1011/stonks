import logging
import warnings
import yaml
import os
import pandas as pd

from stonkslib.indicators.bollinger import bollinger_bands
from stonkslib.indicators.macd import macd
from stonkslib.indicators.obv import obv
from stonkslib.indicators.rsi import rsi

from stonkslib.patterns.doubles import find_doubles
from stonkslib.patterns.triangles import find_triangles
from stonkslib.patterns.wedges import find_wedges
from stonkslib.patterns.head_shoulders import find_head_shoulders

from stonkslib.utils.load_td import load_td

# Suppress the specific UserWarning related to date format inference
warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")

# --- Setup logging to /stonks/log/build_db.log ---
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

# Base directory for output
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TICKER_YAML = os.path.join(BASE_DIR, "..", "tickers.yaml")
BASE_ANALYSIS_DIR = os.path.join(BASE_DIR, "..", "data", "analysis")

def load_ticker_list(yaml_file=TICKER_YAML):
    with open(yaml_file, "r") as f:
        tickers = yaml.safe_load(f)
        print("Tickers list:", tickers)
    result = []
    for category in tickers:
        items = tickers[category]
        if isinstance(items, str):
            items = [items]
        result.extend(items)
    return result

def save_csv(df, ticker, interval, name):
    outdir = os.path.join(BASE_ANALYSIS_DIR, ticker, interval)
    os.makedirs(outdir, exist_ok=True)
    outfile = os.path.join(outdir, f"{name}.csv")
    df.to_csv(outfile)
    return outfile

def aggregate_and_save(ticker, interval):
    status = {}

    # Load DataFrame once
    try:
        df = load_td([ticker], interval)[ticker]
        #df = load_td(ticker, interval)
    except Exception as e:
        logging.error(f"[{ticker} {interval}] Data load error: {e}")
        for key in ["rsi", "macd", "bollinger", "obv"]:
            status[key] = f"error: {e}"
        return status

    # --- RSI Variations ---
    try:
        rsi_periods = [7, 14, 21]
        rsi_df = pd.DataFrame(index=df.index)
        for period in rsi_periods:
            rsi_df[f"RSI_{period}"] = rsi(df, period=period)
        save_csv(rsi_df, ticker, interval, "rsi")
        status["rsi"] = "ok"
    except Exception as e:
        logging.error(f"[{ticker} {interval}] RSI error: {e}")
        status["rsi"] = f"error: {e}"

    # --- MACD Variations ---
    try:
        macd_params = [(12,26,9), (6,19,3), (5,35,5)]
        macd_df = pd.DataFrame(index=df.index)
        for fast, slow, signal in macd_params:
            macd_out = macd(df, short_window=fast, long_window=slow, signal_window=signal)
            # Assumes macd() returns DataFrame with 'MACD' or similar column
            macd_col = macd_out['MACD'] if 'MACD' in macd_out else macd_out.iloc[:,0]
            macd_df[f"MACD_{fast}_{slow}_{signal}"] = macd_col
        save_csv(macd_df, ticker, interval, "macd")
        status["macd"] = "ok"
    except Exception as e:
        logging.error(f"[{ticker} {interval}] MACD error: {e}")
        status["macd"] = f"error: {e}"

    # --- Bollinger Bands Variations ---
    try:
        bb_params = [(20,2), (20,3), (50,2)]
        bb_df = pd.DataFrame(index=df.index)
        for window, num_std in bb_params:
            bands = bollinger_bands(df, window=window, num_std_dev=num_std)
            bb_df[f"BB_upper_{window}_{num_std}"] = bands['Upper_Band']
            bb_df[f"BB_lower_{window}_{num_std}"] = bands['Lower_Band']
        save_csv(bb_df, ticker, interval, "bollinger")
        status["bollinger"] = "ok"
    except Exception as e:
        logging.error(f"[{ticker} {interval}] Bollinger error: {e}")
        status["bollinger"] = f"error: {e}"

    # --- OBV (no variations) ---
    try:
        obv_df = obv(df)
        save_csv(obv_df, ticker, interval, "obv")
        status["obv"] = "ok"
    except Exception as e:
        logging.error(f"[{ticker} {interval}] OBV error: {e}")
        status["obv"] = f"error: {e}"

    # --- Patterns (unchanged) ---
    try:
        doubles = find_doubles(ticker, interval)
        if doubles:
            doubles_df = pd.DataFrame(doubles, columns=["start", "end", "pattern", "confidence"])
        else:
            doubles_df = pd.DataFrame(columns=["start", "end", "pattern", "confidence"])
        save_csv(doubles_df, ticker, interval, "doubles")
        status["doubles"] = "ok"
    except Exception as e:
        logging.error(f"[{ticker} {interval}] Doubles error: {e}")
        status["doubles"] = f"error: {e}"

    try:
        triangles = find_triangles(ticker, interval)
        if triangles:
            triangles_df = pd.DataFrame(triangles, columns=["start", "end", "pattern", "confidence"])
        else:
            triangles_df = pd.DataFrame(columns=["start", "end", "pattern", "confidence"])
        save_csv(triangles_df, ticker, interval, "triangles")
        status["triangles"] = "ok"
    except Exception as e:
        logging.error(f"[{ticker} {interval}] Triangles error: {e}")
        status["triangles"] = f"error: {e}"

    try:
        wedges = find_wedges(ticker, interval)
        if wedges:
            wedges_df = pd.DataFrame(wedges, columns=["start", "end", "pattern", "confidence"])
        else:
            wedges_df = pd.DataFrame(columns=["start", "end", "pattern", "confidence"])
        save_csv(wedges_df, ticker, interval, "wedges")
        status["wedges"] = "ok"
    except Exception as e:
        logging.error(f"[{ticker} {interval}] Wedges error: {e}")
        status["wedges"] = f"error: {e}"

    try:
        hs = find_head_shoulders(ticker, interval)
        if hs:
            hs_df = pd.DataFrame(hs, columns=["left", "head", "right", "pattern", "confidence"])
        else:
            hs_df = pd.DataFrame(columns=["left", "head", "right", "pattern", "confidence"])
        save_csv(hs_df, ticker, interval, "head_shoulders")
        status["head_shoulders"] = "ok"
    except Exception as e:
        logging.error(f"[{ticker} {interval}] Head-Shoulders error: {e}")
        status["head_shoulders"] = f"error: {e}"

    return status

def main(intervals=["1m", "2m", "5m", "15m", "1h", "1d", "1wk"]):
    tickers = load_ticker_list()
    summary = {}
    for ticker in tickers:
        summary[ticker] = {}
        for interval in intervals:
            status = aggregate_and_save(ticker, interval)
            summary[ticker][interval] = status
    # Print/Log a summary at the end
    for ticker in summary:
        for interval in summary[ticker]:
            st = summary[ticker][interval]
            logging.info(f"[{ticker} {interval}] Results: {st}")

if __name__ == "__main__":
    main()
