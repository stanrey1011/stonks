# stonkslib/backtest/head_shoulders.py

import os
import pandas as pd
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PATTERN_BASE = PROJECT_ROOT / "data" / "analysis" / "merged" / "by-patterns"
PRICE_BASE = PROJECT_ROOT / "data" / "analysis" / "merged" / "by-indicators"
OUTPUT_BASE = PROJECT_ROOT / "data" / "analysis" / "backtests" / "patterns" / "head_shoulders"
OUTPUT_BASE.mkdir(parents=True, exist_ok=True)

CONFIDENCE_THRESHOLD = 0.5
START_CASH = 10_000
RISK_PER_TRADE = 0.2

def backtest_head_shoulders(ticker, interval):
    pattern_path = PATTERN_BASE / ticker / f"{interval}.csv"
    price_path = PRICE_BASE / ticker / f"{interval}.csv"
    if not pattern_path.exists() or not price_path.exists():
        logging.warning(f"[!] Missing pattern or price: {pattern_path}, {price_path}")
        return

    patterns = pd.read_csv(pattern_path, index_col=0, parse_dates=True)
    prices = pd.read_csv(price_path, index_col=0, parse_dates=True)
    if "Close" not in prices.columns:
        logging.warning(f"[!] No 'Close' price in {price_path.name}; skipping.")
        return

    cash = START_CASH
    pos = 0
    entry_price = None
    trades = []

    for i, row in patterns.iterrows():
        # Look for the head_shoulders pattern/columns
        pattern = None
        conf = None
        for prefix in ["head_shoulders_", ""]:
            pattern_col = f"{prefix}pattern"
            conf_col = f"{prefix}confidence"
            if pattern_col in row and conf_col in row:
                pattern = row[pattern_col]
                conf = row[conf_col]
                break

        if pd.isna(pattern) or pd.isna(conf) or float(conf) < CONFIDENCE_THRESHOLD:
            continue

        # Only act if pattern is found
        trade_time = i if not isinstance(i, int) else row.get("Date", None)
        if pd.isna(trade_time):
            continue
        close = prices["Close"].get(trade_time, None)
        if pd.isna(close):
            continue

        # SELL on "Head and Shoulders"
        if pattern == "Head and Shoulders":
            if pos > 0:
                cash += pos * close
                trades.append({"action": "SELL", "date": trade_time, "price": close, "size": pos, "cash": cash,
                               "pattern": pattern, "conf": conf, "pnl": (close - entry_price) * pos})
                pos = 0
                entry_price = None
        # Optionally: BUY on "Inverse Head and Shoulders"
        elif pattern == "Inverse Head and Shoulders":  # if you ever implement
            if pos == 0:
                size = int((cash * RISK_PER_TRADE) // close)
                if size > 0:
                    pos = size
                    entry_price = close
                    cash -= pos * close
                    trades.append({"action": "BUY", "date": trade_time, "price": close, "size": pos, "cash": cash,
                                   "pattern": pattern, "conf": conf})

    # Liquidate at end
    if pos > 0:
        last_price = prices["Close"].iloc[-1]
        cash += pos * last_price
        trades.append({"action": "SELL_END", "date": prices.index[-1], "price": last_price, "size": pos, "cash": cash,
                       "pnl": (last_price-entry_price)*pos})

    # Output
    results_df = pd.DataFrame(trades)
    out_dir = OUTPUT_BASE / ticker
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{interval}.csv"
    results_df.to_csv(out_file, index=False)
    total_pnl = results_df.get("pnl", pd.Series([0])).sum()
    logging.info(f"[✓] Backtest complete: {ticker} ({interval}) → {out_file}")
    logging.info(f"    Final cash: {cash:.2f}, Net P&L: {total_pnl:.2f}, Trades: {len(results_df)//2}")

def run_all_backtests(strategy=None):
    intervals = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]
    tickers = [d.name for d in PATTERN_BASE.iterdir() if d.is_dir()]
    for ticker in tickers:
        for interval in intervals:
            backtest_head_shoulders(ticker, interval)

if __name__ == "__main__":
    run_all_backtests()
