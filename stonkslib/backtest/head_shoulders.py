# stonkslib/backtest/head_shoulders.py
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
logger = setup_logging(PROJECT_ROOT / "log", "head_shoulders.log")

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
OUTPUT_BASE = PROJECT_ROOT / config["project"]["backtest_dir"] / "patterns" / "head_shoulders"

# Re-setup logging
logger = setup_logging(PROJECT_ROOT / config["project"]["log_dir"], "head_shoulders.log")

CONFIDENCE_THRESHOLD = 0.5
START_CASH = 10_000
RISK_PER_TRADE = 0.2

def backtest_file(filepath, outpath, strat_config, ticker):
    pattern_path = Path(filepath)
    price_path = PRICE_BASE / ticker / f"{Path(filepath).stem}.csv"
    if not pattern_path.exists() or not price_path.exists():
        logger.warning(f"[!] Missing pattern or price: {pattern_path}, {price_path}")
        return

    patterns = pd.read_csv(pattern_path, index_col=0, parse_dates=True)
    prices = pd.read_csv(price_path, index_col=0, parse_dates=True)
    if "Close" not in prices.columns:
        logger.warning(f"[!] No 'Close' price in {price_path.name}; skipping.")
        return

    options_path = OPTIONS_BASE / strat_config["output_dir"] / f"{ticker}.csv"
    options_df = pd.read_csv(options_path) if options_path.exists() else pd.DataFrame()

    cash = START_CASH
    pos = 0
    entry_price = None
    trades = []

    min_dte = strat_config.get("min_dte", 21)
    max_dte = strat_config.get("max_dte", 9999)
    option_type = strat_config.get("option_type", "calls")

    for i, row in patterns.iterrows():
        pattern = None
        conf = None
        for prefix in ["head(world)_shoulders_", ""]:
            pattern_col = f"{prefix}pattern"
            conf_col = f"{prefix}confidence"
            if pattern_col in row and conf_col in row:
                pattern = row[pattern_col]
                conf = row[conf_col]
                break

        if pd.isna(pattern) or pd.isna(conf) or float(conf) < CONFIDENCE_THRESHOLD:
            continue

        trade_time = i if not isinstance(i, int) else row.get("Date", None)
        if pd.isna(trade_time):
            continue

        if not options_df.empty:
            current_date = pd.to_datetime(trade_time).date()
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

        if pattern == "Head and Shoulders" and pos > 0:
            cash += pos * close
            trades.append({"action": "SELL", "date": trade_time, "price": close, "size": pos, "cash": cash,
                           "pattern": pattern, "conf": conf, "pnl": (close - entry_price) * pos})
            pos = 0
            entry_price = None
        elif pattern == "Inverse Head and Shoulders" and pos == 0:
            size = int((cash * RISK_PER_TRADE) // close)
            if size > 0:
                pos = size
                entry_price = close
                cash -= pos * close
                trades.append({"action": "BUY", "date": trade_time, "price": close, "size": pos, "cash": cash,
                               "pattern": pattern, "conf": conf})

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
        "strategy": strat_config.get("name", "head_shoulders"),
        "metrics": {"final_cash": cash, "net_pnl": total_pnl, "trades": len(results_df) // 2}
    }
    json_outpath = OUTPUT_BASE / f"{strat_config.get('name', 'head_shoulders')}_{ticker}.json"
    json_outpath.parent.mkdir(parents=True, exist_ok=True)
    with open(json_outpath, "w") as f:
        json.dump(result, f)
    logger.info(f"[✓] Backtest complete: {ticker} ({Path(filepath).stem}) → {outpath}, JSON: {json_outpath}")
    logger.info(f"    Final cash: {cash:.2f}, Net P&L: {total_pnl:.2f}, Trades: {len(results_df)//2}")

def run_all_backtests(df=None, strat_config=None, ticker=None, output_dir=OUTPUT_BASE):
    if df is not None and ticker is not None and strat_config is not None:
        outdir = output_dir / "indicators" / ticker
        outdir.mkdir(parents=True, exist_ok=True)
        outpath = outdir / f"{strat_config.get('name', 'indicators')}.csv"
        backtest_file(df, outpath, strat_config, ticker)
    else:
        intervals = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]
        tickers = [d.name for d in (TICKER_DATA_DIR / "analysis" / "merged" / "by-indicators").iterdir() if d.is_dir()]
        for ticker in tickers:
            for interval in intervals:
                input_file = TICKER_DATA_DIR / "analysis" / "merged" / "by-indicators" / ticker / f"{interval}.csv"
                outdir = output_dir / "indicators" / ticker
                outpath = outdir / f"{interval}.csv"
                if input_file.exists():
                    backtest_file(input_file, outpath, strat_config or {}, ticker)