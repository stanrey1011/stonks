# stonkslib/backtest/doubles.py

import os
import pandas as pd
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PATTERN_DIR = PROJECT_ROOT / "data" / "analysis" / "merged" / "by-patterns"
PRICE_DIR = PROJECT_ROOT / "data" / "analysis" / "merged" / "by-indicators"
OUTPUT_BASE = PROJECT_ROOT / "data" / "analysis" / "backtests" / "doubles"   # <--- FIXED path

START_CASH = 10_000
RISK_PER_TRADE = 0.2
CONFIDENCE_THRESHOLD = 0.5

def get_col(row, candidates):
    for c in candidates:
        if c in row and not pd.isna(row[c]):
            return row[c]
    return None

def backtest_file(pattern_path, price_path, out_dir, interval):
    patdf = pd.read_csv(pattern_path)
    pricedf = pd.read_csv(price_path, index_col=0, parse_dates=True)
    if "Close" not in pricedf.columns:
        logging.warning(f"[!] No 'Close' column in {price_path.name}; skipping.")
        return

    trades = []
    cash = START_CASH
    pos = 0
    entry_price = None
    pos_size = 0

    for _, row in patdf.iterrows():
        pattern = get_col(row, ["doubles_pattern", "pattern"])
        conf = get_col(row, ["doubles_confidence", "confidence"])
        date = get_col(row, ["Date", "start", "left"])

        if pattern is None or conf is None or date is None:
            continue
        try:
            conf = float(conf)
        except Exception:
            continue
        if conf < CONFIDENCE_THRESHOLD:
            continue

        price_row = pricedf[pricedf.index == pd.to_datetime(date)]
        if price_row.empty:
            price_row = pricedf.loc[pricedf.index.asof(pd.to_datetime(date)):].head(1)
        if price_row.empty:
            continue
        close = price_row["Close"].iloc[0]

        if pattern == "Double Bottom" and pos == 0:
            size = (cash * RISK_PER_TRADE) // close
            if size > 0:
                pos = 1
                pos_size = size
                entry_price = close
                cash -= size * close
                trades.append({"action": "BUY", "date": date, "confidence": conf, "price": close, "pos_size": size, "cash": cash, "pnl": None})
        elif pattern == "Double Top" and pos == 1:
            cash += pos_size * close
            pnl = (close - entry_price) * pos_size
            trades.append({"action": "SELL", "date": date, "confidence": conf, "price": close, "pos_size": pos_size, "cash": cash, "pnl": pnl})
            pos = 0
            pos_size = 0
            entry_price = None

    # Liquidate if still open at end
    if pos == 1 and entry_price is not None:
        last_close = pricedf["Close"].iloc[-1]
        cash += pos_size * last_close
        pnl = (last_close - entry_price) * pos_size
        trades.append({"action": "SELL_END", "date": pricedf.index[-1], "confidence": None, "price": last_close, "pos_size": pos_size, "cash": cash, "pnl": pnl})

    results_df = pd.DataFrame(trades)
    # NEW: Output to pattern-style folder
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{interval}.csv"
    results_df.to_csv(out_file, index=False)
    logging.info(f"[✓] Backtest complete: {pattern_path.name} → {out_file}")

    total_pnl = results_df.get("pnl", pd.Series([0])).sum()
    logging.info(f"    Final cash: {cash:.2f}, Net P&L: {total_pnl:.2f}, Trades: {len(results_df)//2}")

def run_all_backtests(strategy=None):
    intervals = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]
    for ticker_dir in PATTERN_DIR.iterdir():
        if not ticker_dir.is_dir():
            continue
        ticker = ticker_dir.name
        for interval in intervals:
            pattern_path = PATTERN_DIR / ticker / f"{interval}.csv"
            price_path = PRICE_DIR / ticker / f"{interval}.csv"
            if not pattern_path.exists() or not price_path.exists():
                continue
            out_dir = OUTPUT_BASE / ticker
            backtest_file(pattern_path, price_path, out_dir, interval)

if __name__ == "__main__":
    run_all_backtests()
