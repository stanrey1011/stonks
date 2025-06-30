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
        # --- Indicator columns ---
        rsi = row.get("rsi_RSI_7")
        macd = row.get("macd_MACD_12_26_9")
        close = row.get("Close")

        # Double MA columns
        ma_swing = row.get("ma_double_MA_Swing")
        ma_long = row.get("ma_double_MA_Long")
        # Triple MA columns
        ma_short = row.get("ma_triple_MA_Short")
        ma_medium = row.get("ma_triple_MA_Medium")
        ma_long3 = row.get("ma_triple_MA_Long")

        # --- Entry Conditions (choose your strategy) ---
        entry = False
        exit = False
        reason = ""

        # === 1. Classic: RSI + MACD ===
        if pos == 0 and rsi is not None and macd is not None:
            if rsi < 30 and macd > 0:
                entry = True
                reason = "RSI<30 & MACD>0"

        # === 2. Double MA Crossover ===
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

        # === 3. Triple MA Alignment ===
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

        # === Exit Logic ===
        if pos > 0:
            # Classic: RSI > 70 or stop loss
            if rsi is not None and rsi > 70:
                exit = True
                reason = "RSI>70"
            elif close is not None and entry_price is not None and close < 0.9 * entry_price:
                exit = True
                reason = "Stop Loss"
            # Double MA Bearish Crossover
            elif ma_swing is not None and ma_long is not None and prev_idx >= 0:
                prev_row = df.iloc[prev_idx]
                prev_swing = prev_row.get("ma_double_MA_Swing")
                prev_long = prev_row.get("ma_double_MA_Long")
                if prev_swing is not None and prev_long is not None:
                    if prev_swing >= prev_long and ma_swing < ma_long:
                        exit = True
                        reason = "Double MA Bearish Crossover"
            # Triple MA Bearish Alignment
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

        # --- Execute trades ---
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

    # End of period: liquidate any open position
    if pos > 0 and close is not None:
        cash += pos * close
        trades.append({"action": "SELL_END", "date": i, "price": close, "size": pos, "cash": cash,
                       "pnl": (close - entry_price) * pos, "reason": "End of Backtest"})

    # Results to CSV
    results_df = pd.DataFrame(trades)
    results_df.to_csv(outpath, index=False)
    logging.info(f"[✓] Backtest complete: {filepath.name} → {outpath}")

    # Optional: summary
    total_pnl = results_df.get("pnl", pd.Series([0])).sum()
    logging.info(f"    Final cash: {cash:.2f}, Net P&L: {total_pnl:.2f}, Trades: {len(results_df)//2}")

def run_all_backtests(strategy=None):
    for ticker_dir in INPUT_BASE.iterdir():
        if not ticker_dir.is_dir():
            continue
        ticker = ticker_dir.name
        for interval_file in ticker_dir.iterdir():
            if interval_file.suffix == ".csv":
                outdir = OUTPUT_BASE / ticker
                outdir.mkdir(parents=True, exist_ok=True)
                outpath = outdir / f"{interval_file.stem}.csv"
                backtest_file(interval_file, outpath)

if __name__ == "__main__":
    run_all_backtests()
