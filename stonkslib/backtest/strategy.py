import json
import logging
import re
import yaml
import pandas as pd
from pathlib import Path

from stonkslib.indicators.rsi import rsi as calc_rsi
from stonkslib.indicators.macd import macd as calc_macd
from stonkslib.indicators.bollinger import bollinger_bands
from stonkslib.indicators.moving_avg_double import moving_averages
from stonkslib.indicators.supertrend import supertrend as calc_supertrend
from stonkslib.indicators.rsi_divergence import rsi_divergence as calc_rsi_div
from stonkslib.indicators.markov import markov_signals as calc_markov
from stonkslib.indicators.extrema import timing_quality
from stonkslib.strategies.engine import is_v2, build_namespace, entry_signals, exit_signals, confluence_scores
from stonkslib.utils.load_td import load_td

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_BASE = PROJECT_ROOT / "data" / "backtest_results" / "strategy"
logger = logging.getLogger(__name__)


def load_strategy(yaml_path):
    with open(yaml_path) as f:
        return yaml.safe_load(f)


def _ticker_category(ticker):
    try:
        import yaml
        with open(PROJECT_ROOT / "tickers.yaml") as f:
            data = yaml.safe_load(f) or {}
        for category, tickers in data.items():
            if tickers and ticker in tickers:
                return category
    except Exception:
        pass
    return None


def run_strategy_backtest(ticker, interval, strategy, output_dir=None, df_override=None,
                          trailing_stop_pct=None, start_cash_override=None, risk_pct_override=None,
                          per_signal_amount=0):
    """
    trailing_stop_pct: if set (e.g. 0.12 for 12%), disables indicator-based exits and
                       instead exits when price drops more than X% from the post-entry peak.
    per_signal_amount: if > 0, invest exactly this many dollars per buy signal instead of
                       using risk_per_trade % of cash.
    """
    exclude = strategy.get("exclude_categories", [])
    if exclude and _ticker_category(ticker) in exclude:
        logger.info(f"[skip] {ticker} excluded from '{strategy.get('name')}' (category filter)")
        return None

    if df_override is not None:
        df = df_override.copy()
    else:
        data = load_td([ticker], interval)
        df = data.get(ticker)
        if df is None or df.empty:
            logger.warning(f"[!] No data for {ticker} ({interval})")
            return None
        _lookback = {"1wk": 260, "1d": 756, "1h": 504}.get(interval, 252)
        df = df.iloc[-_lookback:]

    # Re-assert ticker after slicing/override so ticker-aware indicators resolve it.
    df.attrs["ticker"] = ticker

    ind = strategy.get("indicators", {})
    risk = strategy.get("risk", {})
    cash = float(start_cash_override if start_cash_override is not None else risk.get("start_cash", 10000))
    actual_start = cash
    total_signal_invested = 0.0
    risk_per_trade = float(risk_pct_override if risk_pct_override is not None else risk.get("risk_per_trade", 0.2))
    stop_loss_pct = float(risk.get("stop_loss_pct", 0.1))
    slippage = float(risk.get("slippage", 0.0005))

    # v2 strategies carry their own entry/exit logic as expressions — evaluate them
    # once up front and drive the loop from the resulting boolean Series. Legacy
    # strategies fall through to the hardcoded per-indicator path below, unchanged.
    _v2 = is_v2(strategy)
    entry_sig = exit_sig = None
    if _v2:
        _ns = build_namespace(df, strategy)
        entry_sig = entry_signals(df, strategy, _ns)
        exit_sig = exit_signals(df, strategy, _ns)
        # Optional confluence gate: require the weighted BUY vote score to clear
        # min_score before an entry fires. min_score=0 (default) leaves entries
        # untouched, preserving parity with the legacy path. Exits are never gated.
        _min_score = float((strategy.get("confluence") or {}).get("min_score", 0) or 0)
        if _min_score > 0:
            _buy_score, _ = confluence_scores(df, strategy, _ns)
            entry_sig = entry_sig & (_buy_score >= _min_score)

    # Compute enabled indicators (legacy path only)
    rsi_series = None
    rsi_overbought = 70
    rsi_oversold = 30
    rsi_cfg = ind.get("rsi", {})
    if not _v2 and rsi_cfg.get("enabled"):
        p = rsi_cfg.get("params", {})
        rsi_overbought = p.get("overbought", 70)
        rsi_oversold = p.get("oversold", 30)
        rsi_series = calc_rsi(df.copy(), period=p.get("period", 14))

    macd_series = None
    macd_cfg = ind.get("macd", {})
    if not _v2 and macd_cfg.get("enabled"):
        p = macd_cfg.get("params", {})
        macd_out = calc_macd(df.copy(), short_window=p.get("short", 12),
                             long_window=p.get("long", 26), signal_window=p.get("signal", 9))
        macd_series = macd_out["MACD"]

    bb_upper = bb_lower = None
    bb_cfg = ind.get("bollinger", {})
    if not _v2 and bb_cfg.get("enabled"):
        p = bb_cfg.get("params", {})
        bb_out = bollinger_bands(df.copy(), window=p.get("window", 20),
                                 num_std_dev=p.get("num_std_dev", 2))
        bb_upper = bb_out["Upper_Band"]
        bb_lower = bb_out["Lower_Band"]

    ma_swing_series = ma_long_series = None
    ma_cfg = ind.get("ma_double", {})
    if not _v2 and ma_cfg.get("enabled"):
        p = ma_cfg.get("params", {})
        ma_out = moving_averages(df.copy(), swing_window=p.get("swing", 20),
                                 long_window=p.get("long", 50), ma_type="EMA")
        ma_swing_series = ma_out["MA_Swing"]
        ma_long_series = ma_out["MA_Long"]

    st_series = None
    st_cfg = ind.get("supertrend", {})
    if not _v2 and st_cfg.get("enabled"):
        p = st_cfg.get("params", {})
        st_series = calc_supertrend(df.copy(), period=p.get("period", 10),
                                    multiplier=p.get("multiplier", 3.0))

    div_series = None
    div_cfg = ind.get("rsi_divergence", {})
    if not _v2 and div_cfg.get("enabled"):
        p = div_cfg.get("params", {})
        div_series = calc_rsi_div(df.copy(), period=p.get("period", 14),
                                  lookback=p.get("lookback", 20))

    mk_series = None
    mk_bull_thr = 0.6
    mk_bear_thr = 0.6
    mk_cfg = ind.get("markov", {})
    if not _v2 and mk_cfg.get("enabled"):
        p = mk_cfg.get("params", {})
        mk_bull_thr = p.get("bull_threshold", 0.6)
        mk_bear_thr = p.get("bear_threshold", 0.6)
        mk_series = calc_markov(df.copy(), states=p.get("states", 3),
                                lookback=p.get("lookback", 60))

    pos = 0.0
    entry_price = None
    peak_price = None   # for trailing stop
    trades = []
    equity_curve = []   # (date, portfolio_value)
    pending = None
    pending_reason = ""

    for idx, (i, row) in enumerate(df.iterrows()):
        open_price = row.get("Open")
        close = row.get("Close")

        # --- Execute pending order at today's open ---
        if pending and open_price and not pd.isna(open_price):
            if pending == "buy" and pos == 0:
                fill = open_price * (1 + slippage)
                if per_signal_amount > 0:
                    amount = min(float(per_signal_amount), cash)
                    size   = amount / fill
                else:
                    amount = cash * risk_per_trade
                    size   = amount / fill
                if size > 0.00001:
                    pos = size
                    entry_price = fill
                    peak_price = fill
                    cash -= amount
                    total_signal_invested += amount
                    trades.append({"action": "BUY", "date": str(i),
                                   "price": round(fill, 4), "size": round(pos, 8),
                                   "cash": round(float(cash), 2), "reason": pending_reason})
            elif pending == "sell" and pos > 0:
                fill = open_price * (1 - slippage)
                cash += pos * fill
                pnl = (fill - entry_price) * pos
                trades.append({"action": "SELL", "date": str(i),
                                "price": round(fill, 4), "size": round(pos, 8),
                                "cash": round(float(cash), 2),
                                "pnl": round(float(pnl), 2), "reason": pending_reason})
                pos = 0
                entry_price = None
                peak_price = None
            pending = None
            pending_reason = ""

        if close is None or pd.isna(close):
            continue

        # --- Equity curve ---
        portfolio_val = float(cash) + (pos * float(close) if pos > 0 else 0)
        equity_curve.append({"date": str(i), "value": round(portfolio_val, 2)})

        # --- Trailing stop ---
        if trailing_stop_pct and pos > 0 and peak_price is not None and pending is None:
            peak_price = max(peak_price, float(close))
            if float(close) < peak_price * (1 - trailing_stop_pct):
                pending = "sell"
                pending_reason = f"Trailing Stop ({trailing_stop_pct:.0%} from ${peak_price:.2f})"
                continue

        # --- v2: drive entries/exits from precomputed expression signals ---
        if _v2:
            if pos == 0 and pending is None:
                if bool(entry_sig.iloc[idx]):
                    pending, pending_reason = "buy", "Entry signal"
            elif pos > 0 and pending is None and not trailing_stop_pct:
                if bool(exit_sig.iloc[idx]):
                    pending, pending_reason = "sell", "Exit signal"
                elif stop_loss_pct > 0 and entry_price and close < entry_price * (1 - stop_loss_pct):
                    pending, pending_reason = "sell", "Stop Loss"
            continue

        # --- Read indicator values for this bar (legacy path) ---
        r  = float(rsi_series.iloc[idx])      if rsi_series      is not None and idx < len(rsi_series)      else None
        m  = float(macd_series.iloc[idx])     if macd_series     is not None and idx < len(macd_series)     else None
        bu = float(bb_upper.iloc[idx])        if bb_upper        is not None and idx < len(bb_upper)        else None
        bl = float(bb_lower.iloc[idx])        if bb_lower        is not None and idx < len(bb_lower)        else None
        sw = float(ma_swing_series.iloc[idx]) if ma_swing_series is not None and idx < len(ma_swing_series) else None
        ml = float(ma_long_series.iloc[idx])  if ma_long_series  is not None and idx < len(ma_long_series)  else None
        mk_bull = float(mk_series["bull_prob"].iloc[idx]) if mk_series is not None and idx < len(mk_series) and not pd.isna(mk_series["bull_prob"].iloc[idx]) else None
        mk_bear = float(mk_series["bear_prob"].iloc[idx]) if mk_series is not None and idx < len(mk_series) and not pd.isna(mk_series["bear_prob"].iloc[idx]) else None

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

            if pending is None and st_series is not None and idx > 0:
                prev_dir = st_series["Direction"].iloc[idx - 1]
                curr_dir = st_series["Direction"].iloc[idx]
                if prev_dir == -1 and curr_dir == 1:
                    pending, pending_reason = "buy", "Supertrend flipped bullish"

            if pending is None and div_series is not None:
                if div_series["Bullish_Divergence"].iloc[idx]:
                    pending, pending_reason = "buy", "Bullish RSI divergence"

            if pending is None and mk_bull is not None and mk_bull > mk_bull_thr:
                pending, pending_reason = "buy", f"Markov P(→bull)={mk_bull:.0%}"

        # --- Generate exit signal — skipped in trailing stop mode ---
        elif pos > 0 and pending is None and not trailing_stop_pct:
            if r is not None and r > rsi_overbought:
                pending, pending_reason = "sell", f"RSI>{rsi_overbought}"
            elif bu is not None and not pd.isna(bu) and close > bu:
                pending, pending_reason = "sell", "Above upper Bollinger Band"
            elif sw is not None and ml is not None and idx > 0:
                prev_sw = float(ma_swing_series.iloc[idx - 1])
                prev_ml = float(ma_long_series.iloc[idx - 1])
                if prev_sw >= prev_ml and sw < ml:
                    pending, pending_reason = "sell", "MA Bearish Crossover"
            elif st_series is not None and idx > 0:
                prev_dir = st_series["Direction"].iloc[idx - 1]
                curr_dir = st_series["Direction"].iloc[idx]
                if prev_dir == 1 and curr_dir == -1:
                    pending, pending_reason = "sell", "Supertrend flipped bearish"
            elif div_series is not None and div_series["Bearish_Divergence"].iloc[idx]:
                pending, pending_reason = "sell", "Bearish RSI divergence"
            elif mk_bear is not None and mk_bear > mk_bear_thr:
                pending, pending_reason = "sell", f"Markov P(→bear)={mk_bear:.0%}"
            elif stop_loss_pct > 0 and entry_price and close < entry_price * (1 - stop_loss_pct):
                pending, pending_reason = "sell", "Stop Loss"

    # --- Close any open position at last bar's close ---
    if pos > 0:
        last_close = float(df["Close"].iloc[-1])
        fill = last_close * (1 - slippage)
        cash += pos * fill
        pnl = (fill - entry_price) * pos
        trades.append({"action": "SELL_END", "date": str(df.index[-1]),
                       "price": round(fill, 4), "size": round(pos, 8),
                       "cash": round(float(cash), 2),
                       "pnl": round(float(pnl), 2), "reason": "End of Backtest"})

    results_df = pd.DataFrame(trades)
    total_pnl = float(results_df["pnl"].sum()) if "pnl" in results_df.columns else 0.0
    num_trades = len([t for t in trades if t["action"] == "BUY"])
    wins = len([t for t in trades if t.get("pnl", 0) > 0])
    win_rate = round(wins / num_trades, 3) if num_trades > 0 else 0.0

    # max drawdown from equity curve
    eq_vals = [e["value"] for e in equity_curve]
    max_dd = 0.0
    if eq_vals:
        peak = eq_vals[0]
        for v in eq_vals:
            peak = max(peak, v)
            dd = (peak - v) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

    # total_invested: for per-signal mode = sum of $ actually deployed; else start_cash
    total_invested = total_signal_invested if per_signal_amount > 0 else actual_start

    # timing quality: how close each fill sat to a local low (buys) / high (sells)
    timing = timing_quality(df, trades)

    metrics = {
        "ticker": ticker,
        "interval": interval,
        "strategy": strategy.get("name", "unknown"),
        "final_cash": round(float(cash), 2),
        "net_pnl": round(float(cash) - actual_start, 2),
        "trades": num_trades,
        "win_rate": win_rate,
        "max_drawdown": round(max_dd, 4),
        "start_cash": actual_start,
        "total_invested": round(total_invested, 2),
        "per_signal_amount": per_signal_amount,
        "slippage_pct": slippage,
        "exit_mode": f"trailing_{int(trailing_stop_pct*100)}pct" if trailing_stop_pct else "indicator",
        **timing,
        "equity_curve": equity_curve,
    }

    strategy_slug = re.sub(r"[^a-z0-9]+", "_", strategy.get("name", "unknown").lower()).strip("_")
    out_dir = Path(output_dir or OUTPUT_BASE) / ticker / interval
    out_dir.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(out_dir / f"{strategy_slug}.csv", index=False)
    with open(out_dir / f"{strategy_slug}_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    logger.info(f"[✓] {ticker} ({interval}) — P&L: ${total_pnl:.2f}, Trades: {num_trades}, Win rate: {win_rate:.1%}")
    return metrics


def run_buy_and_hold(
    df: pd.DataFrame,
    start_cash: float = 10000,
    slippage: float = 0.0005,
    dca_amount: float = 0,
    dca_bars: int = 0,
) -> dict:
    """
    Benchmark: buy at the first bar's open with full capital, hold to the last bar.
    If dca_amount > 0 and dca_bars > 0, add that amount every dca_bars bars and buy
    immediately (simulates paycheck-style contributions).
    """
    df = df.copy()
    cash = float(start_cash)
    pos  = 0.0
    total_invested  = float(start_cash)
    n_contributions = 0
    equity_curve    = []

    for idx, (i, row) in enumerate(df.iterrows()):
        open_price = row.get("Open")
        close      = row.get("Close")

        if dca_amount > 0 and dca_bars > 0 and idx > 0 and idx % dca_bars == 0:
            if open_price and not pd.isna(open_price):
                cash           += float(dca_amount)
                total_invested += float(dca_amount)
                n_contributions += 1

        if open_price and not pd.isna(open_price) and cash > 0:
            fill = float(open_price) * (1 + slippage)
            pos  += cash / fill
            cash  = 0.0

        if close is None or pd.isna(close):
            continue
        equity_curve.append({"date": str(i), "value": round(pos * float(close), 2)})

    final_value = 0.0
    if pos > 0:
        fill        = float(df["Close"].iloc[-1]) * (1 - slippage)
        final_value = pos * fill

    pnl   = final_value - total_invested
    label = f"Buy & Hold + DCA (×{n_contributions})" if n_contributions > 0 else "Buy & Hold"

    eq_vals = [e["value"] for e in equity_curve]
    max_dd  = 0.0
    if eq_vals:
        peak = eq_vals[0]
        for v in eq_vals:
            peak   = max(peak, v)
            dd     = (peak - v) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

    return {
        "strategy":       label,
        "net_pnl":        round(pnl, 2),
        "trades":         1 + n_contributions,
        "win_rate":       1.0 if pnl > 0 else 0.0,
        "max_drawdown":   round(max_dd, 4),
        "start_cash":     start_cash,
        "total_invested": round(total_invested, 2),
        "final_cash":     round(final_value, 2),
        "equity_curve":   equity_curve,
    }
