import json
import logging
import yaml
import pandas as pd
from pathlib import Path

from stonkslib.indicators.rsi import rsi as calc_rsi
from stonkslib.indicators.macd import macd as calc_macd
from stonkslib.indicators.bollinger import bollinger_bands
from stonkslib.indicators.moving_avg_double import moving_averages
from stonkslib.utils.load_td import load_td

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_BASE = PROJECT_ROOT / "data" / "backtest_results" / "strategy"
logger = logging.getLogger(__name__)


def load_strategy(yaml_path):
    with open(yaml_path) as f:
        return yaml.safe_load(f)


def run_strategy_backtest(ticker, interval, strategy, output_dir=None):
    data = load_td([ticker], interval)
    df = data.get(ticker)
    if df is None or df.empty:
        logger.warning(f"[!] No data for {ticker} ({interval})")
        return None

    ind = strategy.get("indicators", {})
    risk = strategy.get("risk", {})
    cash = float(risk.get("start_cash", 10000))
    risk_per_trade = float(risk.get("risk_per_trade", 0.2))
    stop_loss_pct = float(risk.get("stop_loss_pct", 0.1))
    slippage = float(risk.get("slippage", 0.0005))  # 0.05% default

    # Compute enabled indicators
    rsi_series = None
    rsi_overbought = 70
    rsi_oversold = 30
    rsi_cfg = ind.get("rsi", {})
    if rsi_cfg.get("enabled"):
        p = rsi_cfg.get("params", {})
        rsi_overbought = p.get("overbought", 70)
        rsi_oversold = p.get("oversold", 30)
        rsi_series = calc_rsi(df.copy(), period=p.get("period", 14))

    macd_series = None
    macd_cfg = ind.get("macd", {})
    if macd_cfg.get("enabled"):
        p = macd_cfg.get("params", {})
        macd_out = calc_macd(df.copy(), short_window=p.get("short", 12),
                             long_window=p.get("long", 26), signal_window=p.get("signal", 9))
        macd_series = macd_out["MACD"]

    bb_upper = bb_lower = None
    bb_cfg = ind.get("bollinger", {})
    if bb_cfg.get("enabled"):
        p = bb_cfg.get("params", {})
        bb_out = bollinger_bands(df.copy(), window=p.get("window", 20),
                                 num_std_dev=p.get("num_std_dev", 2))
        bb_upper = bb_out["Upper_Band"]
        bb_lower = bb_out["Lower_Band"]

    ma_swing_series = ma_long_series = None
    ma_cfg = ind.get("ma_double", {})
    if ma_cfg.get("enabled"):
        p = ma_cfg.get("params", {})
        ma_out = moving_averages(df.copy(), swing_window=p.get("swing", 20),
                                 long_window=p.get("long", 50), ma_type="EMA")
        ma_swing_series = ma_out["MA_Swing"]
        ma_long_series = ma_out["MA_Long"]

    pos = 0.0
    entry_price = None
    trades = []
    pending = None      # 'buy' or 'sell'
    pending_reason = ""

    for idx, (i, row) in enumerate(df.iterrows()):
        open_price = row.get("Open")
        close = row.get("Close")

        # --- Execute pending order at today's open (next bar after signal) ---
        if pending and open_price and not pd.isna(open_price):
            if pending == "buy" and pos == 0:
                fill = open_price * (1 + slippage)
                size = (cash * risk_per_trade) // fill
                if size > 0:
                    pos = size
                    entry_price = fill
                    cash -= pos * fill
                    trades.append({"action": "BUY", "date": str(i),
                                   "price": round(fill, 4), "size": int(pos),
                                   "cash": round(float(cash), 2), "reason": pending_reason})
            elif pending == "sell" and pos > 0:
                fill = open_price * (1 - slippage)
                cash += pos * fill
                pnl = (fill - entry_price) * pos
                trades.append({"action": "SELL", "date": str(i),
                                "price": round(fill, 4), "size": int(pos),
                                "cash": round(float(cash), 2),
                                "pnl": round(float(pnl), 2), "reason": pending_reason})
                pos = 0
                entry_price = None
            pending = None
            pending_reason = ""

        if close is None or pd.isna(close):
            continue

        # --- Read indicator values for this bar ---
        r  = float(rsi_series.iloc[idx])      if rsi_series      is not None and idx < len(rsi_series)      else None
        m  = float(macd_series.iloc[idx])     if macd_series     is not None and idx < len(macd_series)     else None
        bu = float(bb_upper.iloc[idx])        if bb_upper        is not None and idx < len(bb_upper)        else None
        bl = float(bb_lower.iloc[idx])        if bb_lower        is not None and idx < len(bb_lower)        else None
        sw = float(ma_swing_series.iloc[idx]) if ma_swing_series is not None and idx < len(ma_swing_series) else None
        ml = float(ma_long_series.iloc[idx])  if ma_long_series  is not None and idx < len(ma_long_series)  else None

        bb_and_rsi = bl is not None and rsi_series is not None

        # --- Generate entry signal (fills at next bar's open) ---
        if pos == 0 and pending is None:
            if bb_and_rsi:
                if r < rsi_oversold and not pd.isna(bl) and close < bl:
                    pending, pending_reason = "buy", f"RSI<{rsi_oversold} & below lower BB"
            else:
                if r is not None and m is not None and r < rsi_oversold and m > 0:
                    pending, pending_reason = "buy", f"RSI<{rsi_oversold} & MACD>0"
                elif r is not None and m is None and r < rsi_oversold:
                    pending, pending_reason = "buy", f"RSI<{rsi_oversold}"
                elif bl is not None and not pd.isna(bl) and close < bl:
                    pending, pending_reason = "buy", "Below lower Bollinger Band"

            if pending is None and sw is not None and ml is not None and idx > 0:
                prev_sw = float(ma_swing_series.iloc[idx - 1])
                prev_ml = float(ma_long_series.iloc[idx - 1])
                if prev_sw <= prev_ml and sw > ml:
                    pending, pending_reason = "buy", "MA Bullish Crossover"

        # --- Generate exit signal (fills at next bar's open) ---
        elif pos > 0 and pending is None:
            if r is not None and r > rsi_overbought:
                pending, pending_reason = "sell", f"RSI>{rsi_overbought}"
            elif bu is not None and not pd.isna(bu) and close > bu:
                pending, pending_reason = "sell", "Above upper Bollinger Band"
            elif sw is not None and ml is not None and idx > 0:
                prev_sw = float(ma_swing_series.iloc[idx - 1])
                prev_ml = float(ma_long_series.iloc[idx - 1])
                if prev_sw >= prev_ml and sw < ml:
                    pending, pending_reason = "sell", "MA Bearish Crossover"
            elif stop_loss_pct > 0 and entry_price and close < entry_price * (1 - stop_loss_pct):
                pending, pending_reason = "sell", "Stop Loss"

    # --- Close any open position at last bar's close ---
    if pos > 0:
        last_close = float(df["Close"].iloc[-1])
        fill = last_close * (1 - slippage)
        cash += pos * fill
        pnl = (fill - entry_price) * pos
        trades.append({"action": "SELL_END", "date": str(df.index[-1]),
                       "price": round(fill, 4), "size": int(pos),
                       "cash": round(float(cash), 2),
                       "pnl": round(float(pnl), 2), "reason": "End of Backtest"})

    results_df = pd.DataFrame(trades)
    total_pnl = float(results_df["pnl"].sum()) if "pnl" in results_df.columns else 0.0
    num_trades = len([t for t in trades if t["action"] == "BUY"])
    wins = len([t for t in trades if t.get("pnl", 0) > 0])
    win_rate = round(wins / num_trades, 3) if num_trades > 0 else 0.0

    metrics = {
        "ticker": ticker,
        "interval": interval,
        "strategy": strategy.get("name", "unknown"),
        "final_cash": round(float(cash), 2),
        "net_pnl": round(total_pnl, 2),
        "trades": num_trades,
        "win_rate": win_rate,
        "start_cash": float(risk.get("start_cash", 10000)),
        "slippage_pct": slippage,
    }

    out_dir = Path(output_dir or OUTPUT_BASE) / ticker
    out_dir.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(out_dir / f"{interval}.csv", index=False)
    with open(out_dir / f"{interval}_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    logger.info(f"[✓] {ticker} ({interval}) — P&L: ${total_pnl:.2f}, Trades: {num_trades}, Win rate: {win_rate:.1%}")
    return metrics
