# stonkslib/backtest/indicators.py

import os
import pandas as pd
from pathlib import Path
import logging

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_BASE = PROJECT_ROOT / "data" / "analysis" / "merged" / "by-indicators"
OUTPUT_BASE = PROJECT_ROOT / "data" / "analysis" / "backtests" / "indicators"
OUTPUT_BASE.mkdir(parents=True, exist_ok=True)

# === Basic trade logic parameters ===
START_CASH = 10_000
RISK_PER_TRADE = 0.2  # 20% of portfolio per trade

def backtest_file(filepath, outpath):
    df = pd.read_csv(filepath, index_col=0, parse_dates=True)
    if "Close" not in df.columns:
        logging.warning(f"[!] No 'Close' column in {filepath.name}; skipping.")
        return

    cash = START_CASH
    pos = 0.0
    entry_price = None
    trades = []

    for i, row in df.iterrows():
        # --- Example entry: RSI_7 < 30, MACD_12_26_9 > 0, OBV rising ---
        rsi = row.get("rsi_RSI_7")
        macd = row.get("macd_MACD_12_26_9")
        obv = row.get("obv_OBV")
        close = row.get("Close")
        if pd.isna(rsi) or pd.isna(macd) or pd.isna(close):
            continue

        # Signal: oversold & positive MACD
        if pos == 0 and rsi < 30 and macd > 0:
            size = (cash * RISK_PER_TRADE) // close
            if size > 0:
                pos = size
                entry_price = close
                cash -= pos * close
                trades.append({"action": "BUY", "date": i, "price": close, "size": pos, "cash": cash})

        # Exit: overbought or stop loss (10%)
        elif pos > 0 and (rsi > 70 or close < 0.9 * entry_price):
            cash += pos * close
            trades.append({"action": "SELL", "date": i, "price": close, "size": pos, "cash": cash,
                           "pnl": (close-entry_price)*pos})
            pos = 0
            entry_price = None

    # End of period: liquidate any open position
    if pos > 0:
        cash += pos * close
        trades.append({"action": "SELL_END", "date": i, "price": close, "size": pos, "cash": cash,
                       "pnl": (close-entry_price)*pos})

    # Results to CSV
    results_df = pd.DataFrame(trades)
    results_df.to_csv(outpath, index=False)
    logging.info(f"[✓] Backtest complete: {filepath.name} → {outpath}")

    # Optional: summary
    total_pnl = results_df.get("pnl", pd.Series([0])).sum()
    logging.info(f"    Final cash: {cash:.2f}, Net P&L: {total_pnl:.2f}, Trades: {len(results_df)//2}")

def run_all_backtests():
    for ticker_dir in INPUT_BASE.iterdir():
        if not ticker_dir.is_dir():
            continue
        ticker = ticker_dir.name
        for interval_file in ticker_dir.iterdir():
            if interval_file.suffix == ".csv":
                outname = f"{ticker}_{interval_file.stem}_results.csv"
                outpath = OUTPUT_BASE / outname
                backtest_file(interval_file, outpath)

if __name__ == "__main__":
    run_all_backtests()