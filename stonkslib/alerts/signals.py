import logging
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
from stonkslib.strategies.engine import is_v2, build_namespace, entry_signals, exit_signals, vote_signals
from stonkslib.utils.load_td import load_td

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _weekly_trend(ticker: str) -> str:
    """Determine weekly trend via 20/50 EMA crossover. Returns 'bullish', 'bearish', or 'neutral'."""
    try:
        data = load_td([ticker], "1wk")
        df = data.get(ticker)
        if df is None or df.empty or len(df) < 60:
            return "neutral"
        ma_out = moving_averages(df.tail(100).copy(), swing_window=20, long_window=50, ma_type="EMA")
        swing = ma_out["MA_Swing"].iloc[-1]
        long_ = ma_out["MA_Long"].iloc[-1]
        if pd.isna(swing) or pd.isna(long_):
            return "neutral"
        diff_pct = (swing - long_) / long_
        if diff_pct > 0.005:
            return "bullish"
        elif diff_pct < -0.005:
            return "bearish"
        return "neutral"
    except Exception as e:
        logger.warning(f"[{ticker}] weekly trend check failed: {e}")
        return "neutral"


def _ticker_category(ticker):
    """Return the category (stocks/crypto/etfs) for a ticker from tickers.yaml."""
    try:
        with open(PROJECT_ROOT / "tickers.yaml") as f:
            data = yaml.safe_load(f) or {}
        for category, tickers in data.items():
            if tickers and ticker in tickers:
                return category
    except Exception:
        pass
    return None


def confluence_score(signals, weights=None):
    """Weighted agreement score per direction.

    Sums the weight of each *distinct* source indicator that fired in a given
    direction (so two reasons from the same indicator don't double-count).
    `weights` maps source -> weight; any source not listed defaults to 1.0, which
    reproduces a plain count of agreeing indicators.

    Returns {"BUY": float, "SELL": float}.
    """
    weights = weights or {}
    out = {"BUY": 0.0, "SELL": 0.0}
    seen = {"BUY": set(), "SELL": set()}
    for s in signals:
        t = s.get("type")
        src = s.get("source", "unknown")
        if t not in out or src in seen[t]:
            continue
        seen[t].add(src)
        out[t] += float(weights.get(src, 1.0))
    return out


def check_signals(ticker, interval, strategy, min_signals: int = 1,
                  confirm_weekly: bool = False, llm_interpret: bool = False,
                  llm_model: str = "qwen2.5:7b", min_score: float = 0.0):
    """Check if the latest bar fires an entry or exit signal for a given strategy.

    min_signals:    require at least this many indicators to agree before returning a signal type.
    min_score:      require the weighted confluence score (per direction) to reach this value.
                    0 = disabled. Falls back to the strategy YAML's `confluence.min_score`.
                    Per-indicator weights come from the strategy YAML's `confluence.weights`.
    confirm_weekly: for 1d intervals, require the weekly 20/50 EMA trend to align.
    llm_interpret:  if True, passes fired signals + indicator context to an LLM for conviction
                    scoring and plain-English reasoning, added to each signal dict.
    """
    exclude = strategy.get("exclude_categories", [])
    if exclude:
        category = _ticker_category(ticker)
        if category in exclude:
            return []

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

    # v2 strategies build their signals from the expression engine further down;
    # skip the hardcoded per-indicator compute below (it stays for legacy strategies).
    _v2 = is_v2(strategy)

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
        st_out = calc_supertrend(df.copy(), period=p.get("period", 10),
                                 multiplier=p.get("multiplier", 3.0))
        st_series = st_out

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
    mk_bull = float(mk_series["bull_prob"].iloc[last_idx]) if mk_series is not None and not pd.isna(mk_series["bull_prob"].iloc[last_idx]) else None
    mk_bear = float(mk_series["bear_prob"].iloc[last_idx]) if mk_series is not None and not pd.isna(mk_series["bear_prob"].iloc[last_idx]) else None

    signals = []
    sig = lambda t, reason, source: {"type": t, "reason": reason, "source": source, "ticker": ticker,
                                      "interval": interval, "close": round(float(close), 2), "date": str(date)}

    bb_and_rsi = bl is not None and r is not None  # both enabled — use AND logic

    # --- Entry signals ---
    if bb_and_rsi:
        if r < rsi_oversold and not pd.isna(bl) and close < bl:
            signals.append(sig("BUY", f"RSI={r:.1f} < {rsi_oversold} & below lower BB ${bl:.2f}", "rsi"))
    else:
        if r is not None and m is not None and r < rsi_oversold and m > 0:
            signals.append(sig("BUY", f"RSI={r:.1f} < {rsi_oversold} & MACD>0", "rsi"))
        elif r is not None and m is None and r < rsi_oversold:
            signals.append(sig("BUY", f"RSI={r:.1f} < {rsi_oversold}", "rsi"))

        if bl is not None and not pd.isna(bl) and close < bl:
            signals.append(sig("BUY", f"Price ${close:.2f} below lower BB ${bl:.2f}", "bollinger"))

    if sw is not None and ml is not None:
        prev_sw = float(ma_swing_series.iloc[last_idx - 1])
        prev_ml = float(ma_long_series.iloc[last_idx - 1])
        if prev_sw <= prev_ml and sw > ml:
            signals.append(sig("BUY", "MA Bullish Crossover", "ma_double"))

    # --- Exit signals ---
    if bb_and_rsi:
        if r > rsi_overbought:
            signals.append(sig("SELL", f"RSI={r:.1f} > {rsi_overbought}", "rsi"))
        if bu is not None and not pd.isna(bu) and close > bu:
            signals.append(sig("SELL", f"Price ${close:.2f} above upper BB ${bu:.2f}", "bollinger"))
    else:
        if r is not None and r > rsi_overbought:
            signals.append(sig("SELL", f"RSI={r:.1f} > {rsi_overbought}", "rsi"))
        if bu is not None and not pd.isna(bu) and close > bu:
            signals.append(sig("SELL", f"Price ${close:.2f} above upper BB ${bu:.2f}", "bollinger"))

    if sw is not None and ml is not None:
        prev_sw = float(ma_swing_series.iloc[last_idx - 1])
        prev_ml = float(ma_long_series.iloc[last_idx - 1])
        if prev_sw >= prev_ml and sw < ml:
            signals.append(sig("SELL", "MA Bearish Crossover", "ma_double"))

    # --- Supertrend signals ---
    if st_series is not None and last_idx >= 1:
        prev_dir = st_series["Direction"].iloc[last_idx - 1]
        curr_dir = st_series["Direction"].iloc[last_idx]
        if prev_dir == -1 and curr_dir == 1:
            signals.append(sig("BUY", "Supertrend flipped bullish", "supertrend"))
        elif prev_dir == 1 and curr_dir == -1:
            signals.append(sig("SELL", "Supertrend flipped bearish", "supertrend"))

    # --- RSI Divergence signals ---
    if div_series is not None:
        if div_series["Bullish_Divergence"].iloc[last_idx]:
            rsi_val = div_series["RSI"].iloc[last_idx]
            signals.append(sig("BUY", f"Bullish RSI divergence (RSI={rsi_val:.1f})", "rsi_divergence"))
        if div_series["Bearish_Divergence"].iloc[last_idx]:
            rsi_val = div_series["RSI"].iloc[last_idx]
            signals.append(sig("SELL", f"Bearish RSI divergence (RSI={rsi_val:.1f})", "rsi_divergence"))

    # --- Markov signals ---
    if mk_bull is not None and mk_bull > mk_bull_thr:
        signals.append(sig("BUY", f"Markov P(→bull)={mk_bull:.0%}", "markov"))
    if mk_bear is not None and mk_bear > mk_bear_thr:
        signals.append(sig("SELL", f"Markov P(→bear)={mk_bear:.0%}", "markov"))

    # ── v2: build signals from the expression engine ──────────────────────────
    # Per-indicator confluence votes (drive the tunable Confluence page) plus the
    # strategy's own entry/exit expression as an authoritative composite signal.
    if _v2:
        _ns = build_namespace(df, strategy)
        votes = vote_signals(df, strategy, _ns)
        for direction in ("BUY", "SELL"):
            for src, series in votes[direction].items():
                if bool(series.iloc[last_idx]):
                    signals.append(sig(direction, f"{src} {direction.lower()} vote", src))
        if bool(entry_signals(df, strategy, _ns).iloc[last_idx]) and not any(s["type"] == "BUY" for s in signals):
            signals.append(sig("BUY", "Entry signal", "strategy"))
        if bool(exit_signals(df, strategy, _ns).iloc[last_idx]) and not any(s["type"] == "SELL" for s in signals):
            signals.append(sig("SELL", "Exit signal", "strategy"))

    if not signals:
        return []

    # ── confluence scoring + gating ───────────────────────────────────────────
    conf_cfg = strategy.get("confluence", {}) or {}
    weights = conf_cfg.get("weights", {}) or {}
    scores = confluence_score(signals, weights)
    for s in signals:
        s["confluence"] = round(scores.get(s["type"], 0.0), 2)

    if min_signals > 1:
        buys  = [s for s in signals if s["type"] == "BUY"]
        sells = [s for s in signals if s["type"] == "SELL"]
        signals = []
        if len(buys) >= min_signals:
            signals.extend(buys)
        if len(sells) >= min_signals:
            signals.extend(sells)
        if not signals:
            logger.info(f"[{ticker}] filtered — confluence below {min_signals}")
            return []

    # weighted score gate — generalises min_signals when indicators carry weights
    score_threshold = min_score if min_score > 0 else float(conf_cfg.get("min_score", 0) or 0)
    if score_threshold > 0:
        signals = [s for s in signals if s["confluence"] >= score_threshold]
        if not signals:
            logger.info(f"[{ticker}] filtered — confluence score below {score_threshold}")
            return []

    # ── weekly trend confirmation ─────────────────────────────────────────────
    if confirm_weekly and interval == "1d":
        trend = _weekly_trend(ticker)
        if trend == "bullish":
            signals = [s for s in signals if s["type"] == "BUY"]
        elif trend == "bearish":
            signals = [s for s in signals if s["type"] == "SELL"]
        else:
            logger.info(f"[{ticker}] filtered — weekly trend is neutral")
            return []
        for s in signals:
            s["reason"] += f"  [weekly: {trend}]"
        if not signals:
            logger.info(f"[{ticker}] filtered — signal direction conflicts with weekly trend ({trend})")
            return []

    # ── LLM interpretation ────────────────────────────────────────────────────
    if llm_interpret:
        from stonkslib.llm.interpreter import interpret_signal

        # build indicator context for the last 10 bars
        n = 10
        indicator_data = {
            "dates": [str(d) for d in df.index[-n:]],
            "close": df["Close"].iloc[-n:].tolist(),
        }
        if rsi_series is not None:
            indicator_data["rsi"] = rsi_series.iloc[-n:].tolist()
        if macd_series is not None:
            indicator_data["macd"] = macd_series.iloc[-n:].tolist()
        if bb_upper is not None and bb_lower is not None:
            mid = (bb_upper + bb_lower) / 2
            bb_width = bb_upper - bb_lower
            indicator_data["bb_pct"] = [
                round((c - m) / w * 100, 1) if w > 0 else 0
                for c, m, w in zip(
                    df["Close"].iloc[-n:],
                    mid.iloc[-n:],
                    bb_width.iloc[-n:],
                )
            ]
        if ma_swing_series is not None and ma_long_series is not None:
            indicator_data["ma_pos"] = [
                "swing>long" if s > l else "swing<long"
                for s, l in zip(
                    ma_swing_series.iloc[-n:],
                    ma_long_series.iloc[-n:],
                )
            ]
        if st_series is not None:
            indicator_data["st_dir"] = [
                "bullish" if d == 1 else "bearish"
                for d in st_series["Direction"].iloc[-n:]
            ]
        if mk_series is not None:
            indicator_data["mk_bull_prob"] = [
                round(v, 3) if not pd.isna(v) else None
                for v in mk_series["bull_prob"].iloc[-n:]
            ]
            indicator_data["mk_bear_prob"] = [
                round(v, 3) if not pd.isna(v) else None
                for v in mk_series["bear_prob"].iloc[-n:]
            ]

        weekly_trend = _weekly_trend(ticker) if interval == "1d" else "n/a"
        interp = interpret_signal(
            ticker=ticker,
            interval=interval,
            signals=signals,
            indicator_data=indicator_data,
            weekly_trend=weekly_trend,
            model=llm_model,
        )
        logger.info(
            f"[{ticker}] LLM: {interp['conviction']} conviction — {interp['reasoning']}"
        )
        for s in signals:
            s["llm_conviction"] = interp["conviction"]
            s["llm_reasoning"]  = interp["reasoning"]

    return signals
