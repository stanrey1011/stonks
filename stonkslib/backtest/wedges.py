import os
import pandas as pd
from pathlib import Path
import logging
import yaml
import json
from stonkslib.utils.logging import setup_logging

# Load configuration
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

# Setup logging (fallback)
logger = setup_logging(PROJECT_ROOT / "log", "wedges.log")

# Load config.yaml with error handling
try:
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)
    if config is None:
        raise ValueError("config.yaml is empty or invalid")
except FileNotFoundError:
    logger.error(f"[!] Config file not found at {CONFIG_PATH}")
    config = {"project": {"ticker_data_dir": "data/ticker_data/raw", "options_data_dir": "data/options_data/raw", "backtest_dir": "data/backtest_results", "log_dir": "log"}}
except Exception as e:
    logger.error(f"[!] Error loading config.yaml: {e}")
    config = {"project": {"ticker_data_dir": "data/ticker_data/raw", "options_data_dir": "data/options_data/raw", "backtest_dir": "data/backtest_results", "log_dir": "log"}}

PATTERN_BASE = PROJECT_ROOT / config["project"]["ticker_data_dir"] / "analysis" / "merged" / "by-patterns"
PRICE_BASE = PROJECT_ROOT / config["project"]["ticker_data_dir"] / "analysis" / "merged" / "by-indicators"
OPTIONS_BASE = PROJECT_ROOT / config["project"]["options_data_dir"]
OUTPUT_BASE = PROJECT_ROOT / config["project"]["backtest_dir"] / "patterns" / "wedges"

# Re-setup logging
logger = setup_logging(PROJECT_ROOT / config["project"]["log_dir"], "wedges.log")

DEFAULT_CONFIDENCE_THRESHOLD = 0.5
START_CASH = 10_000
RISK_PER_TRADE = 0.2

def backtest_file(filepath, outpath, strat_config, ticker):
    pattern_file = Path(filepath)
    price_file = PRICE_BASE / ticker / f"{Path(filepath).stem}.csv"
    if not pattern_file.exists() or not price_file.exists():
        logger.warning(f"[!] Missing: {pattern_file} or {price_file}")
        return

    options_path = OPTIONS_BASE / strat_config["output_dir"] / f"{ticker}.csv"
    options_df = pd.read_csv(options_path) if options_path.exists() else pd.DataFrame()

    pat = pd.read_csv(pattern_file, index_col=0, parse_dates=True)
    prices = pd.read_csv(price_file, index_col=0, parse_dates=True)
    if "Close" not in prices.columns:
        logger.warning(f"[!] No 'Close' price in {price_file.name}; skipping.")
        return

    threshold = strat_config.get("confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD)
    min_dte = strat_config.get("min_dte", 21)
    max_dte = strat_config.get("max_dte", 9999)
    option_type = strat_config.get("option_type", "calls")

    cash = START_CASH
    pos = 0
    entry_price = None
    trades = []

    for idx, row in pat.iterrows():
        pattern = row.get("wedges_pattern")
        conf = row.get("wedges_confidence")
        date = row.get("Date")
        if pd.isna(pattern) or pd.isna(conf) or pd.isna(date) or float(conf) < threshold:
            continue

        try:
            trade_time = pd.to_datetime(date, utc=True)
        except Exception:
            continue

        if not options_df.empty:
            current_date = trade_time.date()
            options_subset = options_df[
                (pd.to_datetime(options_df["expirationDate"]).dt.date >= current_date) &
                (options_df["daysToExpiration"] >= min_dte) &
                (options_df["daysToExpiration"] <= max_dte) &
                (options_df["optionType"] == option_type)
            ]
            close = options_subset["lastPrice"].mean() if not options_subset.empty else prices["Close"].get(trade_time, None)
        else:
            close = prices["Close"].get(trade_time, None)

        if pd.isna(close):
            continue

        if pattern == "Falling Wedge" and pos == 0:
            size = int((cash * RISK_PER_TRADE) // close)
            if size > 0:
                pos = size
                entry_price = close
                cash -= pos * close
                trades.append({"action": "BUY", "date": trade_time, "price": close, "size": pos, "cash": cash, "pattern": pattern, "conf": conf})
        elif pattern == "Rising Wedge" and pos > 0:
            cash += pos * close
            trades.append({"action": "SELL", "date": trade_time, "price": close, "size": pos, "cash": cash, "pattern": pattern, "conf": conf,
                           "pnl": (close - entry_price) * pos})
            pos = 0
            entry_price = None

    if pos > 0:
        last_price = prices["Close"].iloc[-1]
        cash += pos * last_price
        trades.append({"action": "SELL_END", "date": prices.index[-1], "price": last_price, "size": pos, "cash": cash,
                       "pnl": (last_price - entry_price) * pos})

    results_df = pd.DataFrame(trades)
    outpath.parent.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(outpath, index=False)

    total_pnl = results_df.get("pnl", pd.Series([0])).sum()
    result = {
        "symbol": ticker,
        "strategy": strat_config.get("name", "wedges"),
        "metrics": {"final_cash": cash, "net_pnl": total_pnl, "trades": len(results_df) // 2}
    }
    json_outpath = OUTPUT_BASE / f"{strat_config.get('name', 'wedges')}_{ticker}.json"
    json_outpath.parent.mkdir(parents=True, exist_ok=True)
    with open(json_outpath, "w") as f:
        json.dump(result, f)
    logger.info(f"[✓] Backtest complete: {ticker} ({Path(filepath).stem}) → {outpath}, JSON: {json_outpath}")
    logger.info(f"    Final cash: {cash:.2f}, Net P&L: {total_pnl:.2f}, Trades: {len(results_df)//2}")

def run_all_backtests(df=None, strat_config=None, ticker=None, output_dir=OUTPUT_BASE):
    if df is not None and ticker is not None and strat_config is not None:
        outdir = output_dir / ticker
        outdir.mkdir(parents=True, exist_ok=True)
        outpath = outdir / f"{strat_config.get('name', 'wedges')}.csv"
        backtest_file(df, outpath, strat_config, ticker)
    else:
        intervals = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]
        tickers = [d.name for d in PATTERN_BASE.iterdir() if d.is_dir()]
        for ticker in tickers:
            for interval in intervals:
                pattern_file = PATTERN_BASE / ticker / f"{interval}.csv"
                outdir = output_dir / ticker
                outpath = outdir / f"{interval}.csv"
                backtest_file(pattern_file, outpath, strat_config or {}, ticker)