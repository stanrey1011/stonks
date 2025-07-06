# stonkslib/backtest/indicators.py
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
logger = setup_logging(PROJECT_ROOT / "log", "indicators.log")

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

INPUT_BASE = PROJECT_ROOT / config["project"]["ticker_data_dir"]
OPTIONS_BASE = PROJECT_ROOT / config["project"]["options_data_dir"]
OUTPUT_BASE = PROJECT_ROOT / config["project"]["backtest_dir"]

# Re-setup logging with correct log_dir
logger = setup_logging(PROJECT_ROOT / config["project"]["log_dir"], "indicators.log")

START_CASH = 10_000
RISK_PER_TRADE = 0.2

def backtest_file(filepath, outpath, strat_config, ticker):
    df = pd.read_csv(filepath, index_col=0, parse_dates=True)
    if "Close" not in df.columns:
        logger.warning(f"[!] No 'Close' column in {filepath.name}; skipping.")
        return

    options_path = OPTIONS_BASE / strat_config["output_dir"] / f"{ticker}.csv"
    options_df = pd.read_csv(options_path) if options_path.exists() else pd.DataFrame()

    cash = START_CASH
    pos = 0.0
    entry_price = None
    trades = []

    min_dte = strat_config.get("min_dte", 21)
    max_dte = strat_config.get("max_dte", 9999)
    option_type = strat_config.get("option_type", "calls")

    for i, row in df.iterrows():
        if not options_df.empty:
            current_date = pd.to_datetime(i).date()
            options_subset = options_df[
                (pd.to_datetime(options_df["expirationDate"]).dt.date >= current_date) &
                (options_df["daysToExpiration"] >= min_dte) &
                (options_df["daysToExpiration"] <= max_dte) &
                (options_df["optionType"] == option_type)
            ]
            close = options_subset["lastPrice"].mean() if not options_subset.empty else row.get("Close")
        else:
            close = row.get("Close")

        rsi = row.get("rsi_RSI_7")
        macd = row.get("macd_MACD_12_26_9")
        ma_swing = row.get("ma_double_MA_Swing")
        ma_long = row.get("ma_double_MA_Long")
        ma_short = row.get("ma_triple_MA_Short")
        ma_medium = row.get("ma_triple_MA_Medium")
        ma_long3 = row.get("ma_triple_MA_Long")

        entry = False
        exit = False
        reason = ""

        if pos == 0 and rsi is not None and macd is not None:
            rsi_low = strat_config.get("rsi_low", 30)
            if rsi < rsi_low and macd > 0:
                entry = True
                reason = f"RSI<{rsi_low} & MACD>0"

        if pos == 0 and ma_swing is not None and ma_long is not None:
            prev_idx = df.index.get_loc(i) - 1
            if prev_idx >= 0:
                prev_row = df.iloc[prev_idx]
                prev_swing = prev_row.get("ma_double_MA_Swing")
                prev_long = prev_row.get("ma_double_MA_Long")
                if prev_swing is not None and prev_long is not None:
                    if prev_swing <= prev_long and ma_swing > ma_long:
                        entry = True
                        reason = "Double MA Bullish Crossover"

        if pos == 0 and ma_short is not None and ma_medium is not None and ma_long3 is not None:
            prev_idx = df.index.get_loc(i) - 1
            if prev_idx >= 0:
                prev_row = df.iloc[prev_idx]
                prev_short = prev_row.get("ma_triple_MA_Short")
                prev_medium = prev_row.get("ma_triple_MA_Medium")
                prev_long3 = prev_row.get("ma_triple_MA_Long")
                if (prev_short is not None and prev_medium is not None and prev_long3 is not None):
                    if (prev_short <= prev_medium or prev_medium <= prev_long3) and \
                       (ma_short > ma_medium > ma_long3):
                        entry = True
                        reason = "Triple MA Bullish Alignment"

        if pos > 0:
            rsi_high = strat_config.get("rsi_high", 70)
            if rsi is not None and rsi > rsi_high:
                exit = True
                reason = f"RSI>{rsi_high}"
            elif close is not None and entry_price is not None and close < 0.9 * entry_price:
                exit = True
                reason = "Stop Loss"
            elif ma_swing is not None and ma_long is not None and prev_idx >= 0:
                prev_row = df.iloc[prev_idx]
                prev_swing = prev_row.get("ma_double_MA_Swing")
                prev_long = prev_row.get("ma_double_MA_Long")
                if prev_swing is not None and prev_long is not None:
                    if prev_swing >= prev_long and ma_swing < ma_long:
                        exit = True
                        reason = "Double MA Bearish Crossover"
            elif ma_short is not None and ma_medium is not None and ma_long3 is not None and prev_idx >= 0:
                prev_row = df.iloc[prev_idx]
                prev_short = prev_row.get("ma_triple_MA_Short")
                prev_medium = prev_row.get("ma_triple_MA_Medium")
                prev_long3 = prev_row.get("ma_triple_MA_Long")
                if (prev_short is not None and prev_medium is not None and prev_long3 is not None):
                    if (prev_short >= prev_medium or prev_medium >= prev_long3) and \
                       (ma_short < ma_medium < ma_long3):
                        exit = True
                        reason = "Triple MA Bearish Alignment"

        if pos == 0 and entry and close is not None:
            size = (cash * RISK_PER_TRADE) // close
            if size > 0:
                pos = size
                entry_price = close
                cash -= pos * close
                trades.append({"action": "BUY", "date": i, "price": close, "size": pos, "cash": cash, "reason": reason})

        elif pos > 0 and exit and close is not None:
            cash += pos * close
            trades.append({"action": "SELL", "date": i, "price": close, "size": pos, "cash": cash,
                           "pnl": (close - entry_price) * pos, "reason": reason})
            pos = 0
            entry_price = None

    if pos > 0 and close is not None:
        cash += pos * close
        trades.append({"action": "SELL_END", "date": i, "price": close, "size": pos, "cash": cash,
                       "pnl": (close - entry_price) * pos, "reason": "End of Backtest"})

    results_df = pd.DataFrame(trades)
    results_df.to_csv(outpath, index=False)

    total_pnl = results_df.get("pnl", pd.Series([0])).sum()
    result = {
        "symbol": ticker,
        "strategy": strat_config.get("name", "indicators"),
        "metrics": {"final_cash": cash, "net_pnl": total_pnl, "trades": len(results_df) // 2}
    }
    json_outpath = OUTPUT_BASE / f"{strat_config.get('name', 'indicators')}_{ticker}.json"
    json_outpath.parent.mkdir(parents=True, exist_ok=True)
    with open(json_outpath, "w") as f:
        json.dump(result, f)
    logger.info(f"[✓] Backtest complete: {filepath.name} → {outpath}, JSON: {json_outpath}")
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