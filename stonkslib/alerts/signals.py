import logging
import pandas as pd
from pathlib import Path

from stonkslib.indicators.rsi import rsi as calc_rsi
from stonkslib.indicators.macd import macd as calc_macd
from stonkslib.indicators.bollinger import bollinger_bands
from stonkslib.indicators.moving_avg_double import moving_averages
from stonkslib.indicators.supertrend import supertrend as calc_supertrend
from stonkslib.indicators.rsi_divergence import rsi_divergence as calc_rsi_div
from stonkslib.utils.load_td import load_td

logger = logging.getLogger(__name__)


def check_signals(ticker, interval, strategy):
    """Check if the latest bar fires an entry or exit signal for a given strategy."""
    data = load_td([ticker], interval)
    df = data.get(ticker)
    if df is None or df.empty:
        logger.warning(f"[!] No data for {ticker} ({interval})")
        return None

    ind = strategy.get("indicators", {})
    risk = strategy.get("risk", {})
    stop_loss_pct = float(risk.get("stop_loss_pct", 0.1))

    # Need enough bars for indicator warmup — use last 100
    df = df.tail(100).copy()

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

    st_series = None
    st_cfg = ind.get("supertrend", {})
    if st_cfg.get("enabled"):
        p = st_cfg.get("params", {})
        st_out = calc_supertrend(df.copy(), period=p.get("period", 10),
                                 multiplier=p.get("multiplier", 3.0))
        st_series = st_out

    div_series = None
    div_cfg = ind.get("rsi_divergence", {})
    if div_cfg.get("enabled"):
        p = div_cfg.get("params", {})
        div_series = calc_rsi_div(df.copy(), period=p.get("period", 14),
                                  lookback=p.get("lookback", 20))

    # Check only the last two bars (need previous bar for crossover detection)
    last_idx = len(df) - 1
    if last_idx < 1:
        return None

    row = df.iloc[last_idx]
    close = row.get("Close")
    date = df.index[last_idx]

    if close is None or pd.isna(close):
        return None

    r  = float(rsi_series.iloc[last_idx])      if rsi_series      is not None else None
    m  = float(macd_series.iloc[last_idx])     if macd_series     is not None else None
    bu = float(bb_upper.iloc[last_idx])        if bb_upper        is not None else None
    bl = float(bb_lower.iloc[last_idx])        if bb_lower        is not None else None
    sw = float(ma_swing_series.iloc[last_idx]) if ma_swing_series is not None else None
    ml = float(ma_long_series.iloc[last_idx])  if ma_long_series  is not None else None

    signals = []
    sig = lambda t, reason: {"type": t, "reason": reason, "ticker": ticker,
                              "interval": interval, "close": round(float(close), 2), "date": str(date)}

    bb_and_rsi = bl is not None and r is not None  # both enabled — use AND logic

    # --- Entry signals ---
    if bb_and_rsi:
        if r < rsi_oversold and not pd.isna(bl) and close < bl:
            signals.append(sig("BUY", f"RSI={r:.1f} < {rsi_oversold} & below lower BB ${bl:.2f}"))
    else:
        if r is not None and m is not None and r < rsi_oversold and m > 0:
            signals.append(sig("BUY", f"RSI={r:.1f} < {rsi_oversold} & MACD>0"))
        elif r is not None and m is None and r < rsi_oversold:
            signals.append(sig("BUY", f"RSI={r:.1f} < {rsi_oversold}"))

        if bl is not None and not pd.isna(bl) and close < bl:
            signals.append(sig("BUY", f"Price ${close:.2f} below lower BB ${bl:.2f}"))

    if sw is not None and ml is not None:
        prev_sw = float(ma_swing_series.iloc[last_idx - 1])
        prev_ml = float(ma_long_series.iloc[last_idx - 1])
        if prev_sw <= prev_ml and sw > ml:
            signals.append(sig("BUY", "MA Bullish Crossover"))

    # --- Exit signals ---
    if bb_and_rsi:
        if r > rsi_overbought:
            signals.append(sig("SELL", f"RSI={r:.1f} > {rsi_overbought}"))
        if bu is not None and not pd.isna(bu) and close > bu:
            signals.append(sig("SELL", f"Price ${close:.2f} above upper BB ${bu:.2f}"))
    else:
        if r is not None and r > rsi_overbought:
            signals.append(sig("SELL", f"RSI={r:.1f} > {rsi_overbought}"))
        if bu is not None and not pd.isna(bu) and close > bu:
            signals.append(sig("SELL", f"Price ${close:.2f} above upper BB ${bu:.2f}"))

    if sw is not None and ml is not None:
        prev_sw = float(ma_swing_series.iloc[last_idx - 1])
        prev_ml = float(ma_long_series.iloc[last_idx - 1])
        if prev_sw >= prev_ml and sw < ml:
            signals.append(sig("SELL", "MA Bearish Crossover"))

    # --- Supertrend signals ---
    if st_series is not None and last_idx >= 1:
        prev_dir = st_series["Direction"].iloc[last_idx - 1]
        curr_dir = st_series["Direction"].iloc[last_idx]
        if prev_dir == -1 and curr_dir == 1:
            signals.append(sig("BUY", "Supertrend flipped bullish"))
        elif prev_dir == 1 and curr_dir == -1:
            signals.append(sig("SELL", "Supertrend flipped bearish"))

    # --- RSI Divergence signals ---
    if div_series is not None:
        if div_series["Bullish_Divergence"].iloc[last_idx]:
            rsi_val = div_series["RSI"].iloc[last_idx]
            signals.append(sig("BUY", f"Bullish RSI divergence (RSI={rsi_val:.1f})"))
        if div_series["Bearish_Divergence"].iloc[last_idx]:
            rsi_val = div_series["RSI"].iloc[last_idx]
            signals.append(sig("SELL", f"Bearish RSI divergence (RSI={rsi_val:.1f})"))

    return signals if signals else []
