# stonkslib/backtest/wedges.py

import os
import pandas as pd
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PATTERN_DIR = PROJECT_ROOT / "data" / "analysis" / "merged" / "by-patterns"
PRICE_DIR = PROJECT_ROOT / "data" / "analysis" / "merged" / "by-indicators"
OUTPUT_BASE = PROJECT_ROOT / "data" / "analysis" / "backtests" / "patterns" / "wedges"
OUTPUT_BASE.mkdir(parents=True, exist_ok=True)

CONFIDENCE_THRESHOLD = 0.5

def backtest_wedges(ticker, interval):
    pattern_file = PATTERN_DIR / ticker / f"{interval}.csv"
    price_file = PRICE_DIR / ticker / f"{interval}.csv"
    if not pattern_file.exists() or not price_file.exists():
        logging.warning(f"[!] Missing: {pattern_file} or {price_file}")
        return

    pat = pd.read_csv(pattern_file)
    prices = pd.read_csv(price_file, index_col=0, parse_dates=True)
    trades = []
    position = None
    entry_price = None

    for idx, row in pat.iterrows():
        # Only consider rows with a wedge pattern and confidence >= threshold
        pattern = row.get("wedges_pattern")
        conf = row.get("wedges_confidence")
        date = row.get("Date")

        if pd.isna(pattern) or pd.isna(conf) or pd.isna(date):
            continue
        if float(conf) < CONFIDENCE_THRESHOLD:
            continue

        try:
            trade_time = pd.to_datetime(date, utc=True)
        except Exception:
            continue

        # Get close price for the wedge signal
        if trade_time not in prices.index:
            # Fallback: get the closest time (pad with method='bfill')
            trade_time = prices.index[prices.index.get_loc(trade_time, method='nearest')]
        close = prices.loc[trade_time, "Close"] if "Close" in prices.columns else None
        if pd.isna(close):
            continue

        # Simple trade logic: buy falling wedge, sell rising wedge
        if pattern == "Falling Wedge" and position is None:
            trades.append({"action": "BUY", "date": trade_time, "conf": conf, "price": close})
            position = "long"
            entry_price = close
        elif pattern == "Rising Wedge" and position == "long":
            trades.append({"action": "SELL", "date": trade_time, "conf": conf, "price": close,
                           "pnl": close - entry_price})
            position = None

    # Output
    out_dir = OUTPUT_BASE / ticker
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{interval}.csv"
    pd.DataFrame(trades).to_csv(out_file, index=False)
    logging.info(f"[✓] Backtest complete: {out_file} ({len(trades)} trades)")

    # Optional: Print summary
    total_buys = sum(1 for t in trades if t['action'] == 'BUY')
    total_sells = sum(1 for t in trades if t['action'] == 'SELL')
    total_pnl = sum(t.get('pnl', 0) for t in trades if 'pnl' in t)
    print(f"Ticker {ticker} {interval} — Buys: {total_buys}, Sells: {total_sells}, Net P&L: {total_pnl:.2f}")

def main():
    tickers = [d.name for d in PATTERN_DIR.iterdir() if d.is_dir()]
    intervals = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]
    for ticker in tickers:
        for interval in intervals:
            backtest_wedges(ticker, interval)

if __name__ == "__main__":
    main()
