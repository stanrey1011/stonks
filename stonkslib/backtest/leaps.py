"""
LEAP options backtester using Black-Scholes pricing.

Since yfinance doesn't provide historical options data, premiums are approximated
via Black-Scholes using rolling realized volatility from the underlying's price
history. This is directionally sound but will differ from real IV-based pricing.
"""
import json
import logging
import math
import re
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import norm

from stonkslib.indicators.rsi import rsi as calc_rsi
from stonkslib.indicators.macd import macd as calc_macd
from stonkslib.indicators.bollinger import bollinger_bands
from stonkslib.indicators.moving_avg_double import moving_averages
from stonkslib.indicators.supertrend import supertrend as calc_supertrend
from stonkslib.indicators.rsi_divergence import rsi_divergence as calc_rsi_div
from stonkslib.utils.load_td import load_td

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_BASE = PROJECT_ROOT / "data" / "backtest_results" / "leaps"
logger = logging.getLogger(__name__)

RISK_FREE_RATE = 0.045  # ~4.5% T-bill


def _bs_price(S, K, T, sigma, option_type, r=RISK_FREE_RATE):
    """Black-Scholes option price. Returns intrinsic value if T<=0 or sigma<=0."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return max(S - K, 0.0) if option_type == "call" else max(K - S, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if option_type == "call":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    else:
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def _bs_delta(S, K, T, sigma, option_type, r=RISK_FREE_RATE):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 1.0 if option_type == "call" else -1.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return norm.cdf(d1) if option_type == "call" else norm.cdf(d1) - 1.0


def _realized_vol(close_series: pd.Series, window: int = 30) -> pd.Series:
    """Rolling annualized realized volatility from log returns (252-day basis)."""
    log_ret = np.log(close_series / close_series.shift(1))
    return log_ret.rolling(window).std() * math.sqrt(252)


def run_leaps_backtest(ticker, interval, strategy, option_type="auto",
                       leap_days=365, strike_moneyness=1.0,
                       stop_loss_pct=0.50, start_cash=10000,
                       risk_per_trade=0.20, output_dir=None):
    """
    Backtest LEAP call or put options using Black-Scholes pricing.

    Args:
        ticker: ticker symbol
        interval: price interval (1d or 1wk recommended)
        strategy: loaded strategy dict
        option_type: "call", "put", or "auto" (derives from net signal direction)
        leap_days: option duration at entry in days (default 365)
        strike_moneyness: strike as fraction of spot at entry (1.0 = ATM)
        stop_loss_pct: close if option loses this fraction of entry premium
        start_cash: starting capital
        risk_per_trade: fraction of cash to risk per trade
    """
    data = load_td([ticker], interval)
    df = data.get(ticker)
    if df is None or df.empty:
        logger.warning(f"[!] No data for {ticker} ({interval})")
        return None

    ind = strategy.get("indicators", {})

    # --- Build indicators ---
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
        macd_series = calc_macd(df.copy(), short_window=p.get("short", 12),
                                long_window=p.get("long", 26),
                                signal_window=p.get("signal", 9))["MACD"]

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

    st_series = None
    st_cfg = ind.get("supertrend", {})
    if st_cfg.get("enabled"):
        p = st_cfg.get("params", {})
        st_series = calc_supertrend(df.copy(), period=p.get("period", 10),
                                    multiplier=p.get("multiplier", 3.0))

    div_series = None
    div_cfg = ind.get("rsi_divergence", {})
    if div_cfg.get("enabled"):
        p = div_cfg.get("params", {})
        div_series = calc_rsi_div(df.copy(), period=p.get("period", 14),
                                  lookback=p.get("lookback", 20))

    vol_series = _realized_vol(df["Close"])

    bar_years = 1 / 52 if interval == "1wk" else 1 / 252

    # --- Backtest state ---
    cash = float(start_cash)
    contracts = 0
    entry_premium = None
    entry_T = None
    entry_strike = None
    entry_option_type = None
    entry_bar_idx = None
    trades = []
    pending = None        # "enter" or "exit"
    pending_reason = ""
    pending_signal = None  # "call" or "put"

    for idx in range(len(df)):
        row = df.iloc[idx]
        S = float(row.get("Close") or 0)
        S_open = float(row.get("Open") or S)
        date = df.index[idx]

        if S <= 0:
            continue

        vol = float(vol_series.iloc[idx]) if not pd.isna(vol_series.iloc[idx]) else 0.30
        vol = max(vol, 0.05)

        # --- Execute pending order at next bar open ---
        if pending and S_open > 0:
            if pending == "enter" and contracts == 0:
                T = leap_days / 365.0
                K = round(S_open * strike_moneyness, 2)
                premium = _bs_price(S_open, K, T, vol, pending_signal)
                # Fixed sizing on start_cash — avoids compounding distortion over many trades
                n = max(1, int((start_cash * risk_per_trade) / (premium * 100))) if premium > 0 else 0
                if n > 0 and premium > 0:
                    cost = min(n * premium * 100, cash)  # never spend more than available
                    n = int(cost / (premium * 100))      # recalc contracts after cap
                    if n == 0:
                        pending = None
                        pending_reason = ""
                        pending_signal = None
                        continue
                    cost = n * premium * 100
                    cash -= cost
                    contracts = n
                    entry_premium = premium
                    entry_T = T
                    entry_strike = K
                    entry_option_type = pending_signal
                    entry_bar_idx = idx
                    delta = _bs_delta(S_open, K, T, vol, pending_signal)
                    trades.append({
                        "action": "BUY_LEAP",
                        "option_type": pending_signal.upper(),
                        "date": str(date),
                        "spot": round(S_open, 2),
                        "strike": K,
                        "T_years": round(T, 3),
                        "premium": round(premium, 2),
                        "contracts": n,
                        "delta": round(delta, 3),
                        "vol": round(vol, 3),
                        "cash": round(cash, 2),
                        "reason": pending_reason,
                    })

            elif pending == "exit" and contracts > 0:
                elapsed = (idx - entry_bar_idx) * bar_years
                remaining_T = max(entry_T - elapsed, 0.001)
                exit_premium = _bs_price(S_open, entry_strike, remaining_T, vol, entry_option_type)
                proceeds = contracts * exit_premium * 100
                cost_basis = contracts * entry_premium * 100
                pnl = proceeds - cost_basis
                cash += proceeds
                trades.append({
                    "action": "SELL_LEAP",
                    "option_type": entry_option_type.upper(),
                    "date": str(date),
                    "spot": round(S_open, 2),
                    "strike": entry_strike,
                    "remaining_T": round(remaining_T, 3),
                    "premium": round(exit_premium, 2),
                    "contracts": contracts,
                    "vol": round(vol, 3),
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl / cost_basis * 100, 1) if cost_basis > 0 else 0,
                    "cash": round(cash, 2),
                    "reason": pending_reason,
                })
                contracts = 0
                entry_premium = entry_T = entry_strike = entry_option_type = entry_bar_idx = None

            pending = None
            pending_reason = ""
            pending_signal = None

        if S <= 0:
            continue

        # --- Read indicator values ---
        r  = float(rsi_series.iloc[idx])      if rsi_series      is not None and idx < len(rsi_series)      else None
        m  = float(macd_series.iloc[idx])     if macd_series     is not None and idx < len(macd_series)     else None
        bu = float(bb_upper.iloc[idx])        if bb_upper        is not None and idx < len(bb_upper)        else None
        bl = float(bb_lower.iloc[idx])        if bb_lower        is not None and idx < len(bb_lower)        else None
        sw = float(ma_swing_series.iloc[idx]) if ma_swing_series is not None and idx < len(ma_swing_series) else None
        ml = float(ma_long_series.iloc[idx])  if ma_long_series  is not None and idx < len(ma_long_series)  else None

        bb_and_rsi = bl is not None and rsi_series is not None

        # --- Signal detection (mirrors strategy.py and alerts/signals.py) ---
        buy_signal = sell_signal = False

        if bb_and_rsi:
            if r < rsi_oversold and not pd.isna(bl) and S < bl:
                buy_signal = True
            if r > rsi_overbought:
                sell_signal = True
            if bu is not None and not pd.isna(bu) and S > bu:
                sell_signal = True
        else:
            if r is not None and m is not None and r < rsi_oversold and m > 0:
                buy_signal = True
            elif r is not None and m is None and r < rsi_oversold:
                buy_signal = True
            elif bl is not None and not pd.isna(bl) and S < bl:
                buy_signal = True
            if r is not None and r > rsi_overbought:
                sell_signal = True
            if bu is not None and not pd.isna(bu) and S > bu:
                sell_signal = True

        if sw is not None and ml is not None and idx > 0:
            prev_sw = float(ma_swing_series.iloc[idx - 1])
            prev_ml = float(ma_long_series.iloc[idx - 1])
            if prev_sw <= prev_ml and sw > ml:
                buy_signal = True
            elif prev_sw >= prev_ml and sw < ml:
                sell_signal = True

        if st_series is not None and idx > 0:
            prev_dir = st_series["Direction"].iloc[idx - 1]
            curr_dir = st_series["Direction"].iloc[idx]
            if prev_dir == -1 and curr_dir == 1:
                buy_signal = True
            elif prev_dir == 1 and curr_dir == -1:
                sell_signal = True

        if div_series is not None:
            if div_series["Bullish_Divergence"].iloc[idx]:
                buy_signal = True
            if div_series["Bearish_Divergence"].iloc[idx]:
                sell_signal = True

        # Map option_type to entry direction
        enters_on_buy  = option_type in ("call", "auto")
        enters_on_sell = option_type in ("put",  "auto")

        # --- Entry ---
        if contracts == 0 and pending is None:
            if enters_on_buy and buy_signal:
                pending, pending_reason, pending_signal = "enter", "Bullish signal → CALL", "call"
            elif enters_on_sell and sell_signal:
                pending, pending_reason, pending_signal = "enter", "Bearish signal → PUT", "put"

        # --- Exit / stop-loss ---
        elif contracts > 0 and pending is None:
            elapsed = (idx - entry_bar_idx) * bar_years
            remaining_T = max(entry_T - elapsed, 0.001)
            current_val = _bs_price(S, entry_strike, remaining_T, vol, entry_option_type)

            if current_val < entry_premium * (1 - stop_loss_pct):
                pending, pending_reason = "exit", f"Stop loss ({stop_loss_pct:.0%} of premium)"
            elif remaining_T < 14 / 365:
                pending, pending_reason = "exit", "Approaching expiry (< 2 weeks)"

    # --- Close open position at last bar ---
    if contracts > 0:
        last_S = float(df["Close"].iloc[-1])
        last_vol = float(vol_series.iloc[-1]) if not pd.isna(vol_series.iloc[-1]) else 0.30
        elapsed = (len(df) - 1 - entry_bar_idx) * bar_years
        remaining_T = max(entry_T - elapsed, 0.001)
        exit_premium = _bs_price(last_S, entry_strike, remaining_T, max(last_vol, 0.05), entry_option_type)
        proceeds = contracts * exit_premium * 100
        cost_basis = contracts * entry_premium * 100
        pnl = proceeds - cost_basis
        cash += proceeds
        trades.append({
            "action": "SELL_LEAP_END",
            "option_type": entry_option_type.upper(),
            "date": str(df.index[-1]),
            "spot": round(last_S, 2),
            "strike": entry_strike,
            "remaining_T": round(remaining_T, 3),
            "premium": round(exit_premium, 2),
            "contracts": contracts,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl / cost_basis * 100, 1) if cost_basis > 0 else 0,
            "cash": round(cash, 2),
            "reason": "End of backtest",
        })

    results_df = pd.DataFrame(trades)
    sell_trades = [t for t in trades if "SELL" in t["action"]]
    total_pnl = sum(t.get("pnl", 0) for t in sell_trades)
    num_entries = len([t for t in trades if t["action"] == "BUY_LEAP"])
    wins = len([t for t in sell_trades if t.get("pnl", 0) > 0])
    win_rate = round(wins / num_entries, 3) if num_entries > 0 else 0.0
    avg_pnl_pct = (sum(t.get("pnl_pct", 0) for t in sell_trades) / len(sell_trades)
                   if sell_trades else 0.0)

    metrics = {
        "ticker": ticker,
        "interval": interval,
        "strategy": strategy.get("name", "unknown"),
        "option_type": option_type,
        "leap_days": leap_days,
        "strike_moneyness": strike_moneyness,
        "stop_loss_pct": stop_loss_pct,
        "final_cash": round(cash, 2),
        "net_pnl": round(total_pnl, 2),
        "trades": num_entries,
        "win_rate": win_rate,
        "avg_pnl_pct": round(avg_pnl_pct, 1),
        "start_cash": start_cash,
        "pricing_note": "Black-Scholes with 30-bar realized vol — approximate",
    }

    strategy_slug = re.sub(r"[^a-z0-9]+", "_", strategy.get("name", "unknown").lower()).strip("_")
    out_dir = Path(output_dir or OUTPUT_BASE) / ticker / interval
    out_dir.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(out_dir / f"{strategy_slug}_{option_type}.csv", index=False)
    with open(out_dir / f"{strategy_slug}_{option_type}_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    logger.info(
        f"[✓] {ticker} LEAP {option_type} ({interval}) — "
        f"P&L: ${total_pnl:.2f}, Trades: {num_entries}, Win: {win_rate:.1%}"
    )
    return metrics
