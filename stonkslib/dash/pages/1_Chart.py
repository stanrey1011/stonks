import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yaml
import pandas as pd
from datetime import date, timedelta

from stonkslib.dash.common import (
    load_watchlist, flat_tickers, load_ticker_data,
    STRATEGY_DIR, INTERVALS,
)

st.set_page_config(page_title="Chart — Stonks", layout="wide")
st.title("Chart")
st.caption("Interactive candlestick chart with volume. Select a strategy from the sidebar to overlay its indicators — params are pulled from your optimized YAMLs automatically. Toggle individual overlays (Bollinger, MA, RSI, MACD) independently of the strategy.")

wl = load_watchlist()
tickers = flat_tickers(wl)
if not tickers:
    st.warning("No tickers in watchlist. Add some on the Watchlist page.")
    st.stop()


def _resolve_strategy(strategy_path: Path, ticker: str) -> tuple[Path, str]:
    opt = STRATEGY_DIR / "optimized"
    p = opt / f"{strategy_path.stem}_{ticker}_optimized.yaml"
    if p.exists():
        return p, "per-ticker optimized"
    p = opt / f"{strategy_path.stem}_optimized.yaml"
    if p.exists():
        return p, "global optimized"
    return strategy_path, "base"


# ── cached indicator functions ────────────────────────────────────────────────
# All take (ticker, interval, *params) so the cache key is hashable primitives.
# Data is already cached in load_ticker_data; indicators cache their own output.

@st.cache_data(ttl=86400, show_spinner=False)
def _get_earnings(ticker: str) -> dict:
    from stonkslib.utils.earnings import get_earnings
    return get_earnings(ticker)


@st.cache_data(ttl=3600, show_spinner=False)
def _get_rsi(ticker: str, interval: str, period: int) -> pd.Series:
    from stonkslib.indicators.rsi import rsi
    df = load_ticker_data(ticker, interval)
    return rsi(df.copy(), period=period)


@st.cache_data(ttl=3600, show_spinner=False)
def _get_macd(ticker: str, interval: str, short: int, long_: int, signal: int) -> pd.DataFrame:
    from stonkslib.indicators.macd import macd
    df = load_ticker_data(ticker, interval)
    return macd(df.copy(), short_window=short, long_window=long_, signal_window=signal)


@st.cache_data(ttl=3600, show_spinner=False)
def _get_bb(ticker: str, interval: str, window: int, num_std: float) -> pd.DataFrame:
    from stonkslib.indicators.bollinger import bollinger_bands
    df = load_ticker_data(ticker, interval)
    return bollinger_bands(df.copy(), window=window, num_std_dev=num_std)


@st.cache_data(ttl=3600, show_spinner=False)
def _get_ma_double(ticker: str, interval: str, swing: int, long_: int) -> pd.DataFrame:
    from stonkslib.indicators.moving_avg_double import moving_averages
    df = load_ticker_data(ticker, interval)
    return moving_averages(df.copy(), swing_window=swing, long_window=long_, ma_type="EMA")


@st.cache_data(ttl=3600, show_spinner=False)
def _get_ma_triple(ticker: str, interval: str, short: int, medium: int, long_: int) -> pd.DataFrame:
    from stonkslib.indicators.moving_avg_triple import moving_averages_triple
    df = load_ticker_data(ticker, interval)
    return moving_averages_triple(df.copy(), short_window=short, medium_window=medium,
                                  long_window=long_, ma_type="EMA")


@st.cache_data(ttl=3600, show_spinner=False)
def _get_markov(ticker: str, interval: str, states: int, lookback: int) -> pd.DataFrame:
    from stonkslib.indicators.markov import markov_signals
    df = load_ticker_data(ticker, interval)
    return markov_signals(df.copy(), states=states, lookback=lookback)


# ── lookback map: label → bars per interval ───────────────────────────────────

_LOOKBACK = {
    "6 months": {"1d": 126,  "1wk": 26,  "1h": 500,  "_": 500},
    "1 year":   {"1d": 252,  "1wk": 52,  "1h": 1000, "_": 1000},
    "2 years":  {"1d": 504,  "1wk": 104, "1h": 2000, "_": 2000},
    "5 years":  {"1d": 1260, "1wk": 260, "1h": 5000, "_": 5000},
    "All":      {"1d": 9999, "1wk": 9999,"1h": 9999, "_": 9999},
}

# ── selectors ─────────────────────────────────────────────────────────────────

col1, col2 = st.columns([3, 1])
with col1:
    ticker = st.selectbox("Ticker", tickers, key="chart_ticker")
with col2:
    interval = st.selectbox("Interval", INTERVALS, key="chart_interval")

strategy_files = sorted(STRATEGY_DIR.glob("*.yaml"))
strategy_names = [yaml.safe_load(p.read_text()).get("name", p.stem) for p in strategy_files]
strategy_map   = dict(zip(strategy_names, strategy_files))

with st.sidebar:
    chosen_name    = st.selectbox("Strategy", ["None"] + strategy_names, key="chart_strategy")
    show_bollinger = st.checkbox("Bollinger Bands",        key="chart_bb")
    show_ma_double = st.checkbox("Double MA (20/50 EMA)", key="chart_ma2")
    show_ma_triple = st.checkbox("Triple MA (9/21/50 EMA)", key="chart_ma3")
    show_macd      = st.checkbox("MACD",                  key="chart_macd")
    show_rsi       = st.checkbox("RSI",                   key="chart_rsi")
    show_markov    = st.checkbox("Markov Regime",         key="chart_markov")
    show_earnings  = st.checkbox("Earnings",              key="chart_earnings")
    show_forward   = st.checkbox("Forward markers (15/30/45d)", key="chart_forward")
    lookback_label = st.selectbox("Lookback", list(_LOOKBACK.keys()), index=2, key="chart_lookback")
    pad_pct        = st.slider("Y-axis padding %", 1, 20, 5, key="chart_pad") / 100

lookback_bars = _LOOKBACK[lookback_label].get(interval, _LOOKBACK[lookback_label]["_"])

# ── load strategy + resolve params ───────────────────────────────────────────

strat       = {}
strat_src   = ""
rsi_params  = {"period": 14, "overbought": 70, "oversold": 30}
macd_params = {"short": 12, "long": 26, "signal": 9}
bb_params   = {"window": 20, "num_std_dev": 2}
ma_double_params = {"swing": 20, "long": 50}
ma_triple_params = {"short": 9, "medium": 21, "long": 50}
markov_params = {"states": 3, "lookback": 60, "bull_threshold": 0.5, "bear_threshold": 0.5}

if chosen_name != "None":
    strat_path, strat_src = _resolve_strategy(strategy_map[chosen_name], ticker)
    strat = yaml.safe_load(strat_path.read_text())
    ind   = strat.get("indicators", {})

    if ind.get("rsi", {}).get("enabled"):
        rsi_params = {**rsi_params, **ind["rsi"].get("params", {})}
        show_rsi = True

    if ind.get("macd", {}).get("enabled"):
        macd_params = {**macd_params, **ind["macd"].get("params", {})}
        show_macd = True

    if ind.get("bollinger", {}).get("enabled"):
        bb_params = {**bb_params, **ind["bollinger"].get("params", {})}
        show_bollinger = True

    if ind.get("ma_double", {}).get("enabled"):
        show_ma_double = True

    if ind.get("ma_triple", {}).get("enabled"):
        show_ma_triple = True

    if ind.get("markov", {}).get("enabled"):
        markov_params = {**markov_params, **ind["markov"].get("params", {})}
        show_markov = True

    badge = {"per-ticker optimized": "🟢 per-ticker opt",
             "global optimized":     "🟡 global opt",
             "base":                 "⚪ base"}.get(strat_src, strat_src)
    st.sidebar.caption(f"Params: **{badge}**")

# ── load + slice price data ───────────────────────────────────────────────────

df_full = load_ticker_data(ticker, interval)
if df_full is None:
    st.error(f"No data for **{ticker}** ({interval}). Run: `stonks pipeline {ticker}`")
    st.stop()

df_full = df_full[~df_full.index.duplicated(keep="last")]
df = df_full.iloc[-lookback_bars:] if len(df_full) > lookback_bars else df_full
asset_type = next((cat for cat, items in wl.items() if items and ticker in items), "unknown")

# ── build subplot layout ──────────────────────────────────────────────────────

show_sub    = show_rsi or show_macd or show_markov
n_rows      = 3 if show_sub else 2
row_heights = [0.60, 0.20, 0.20] if show_sub else [0.75, 0.25]

fig = make_subplots(
    rows=n_rows, cols=1,
    shared_xaxes=True,
    row_heights=row_heights,
    vertical_spacing=0.03,
)

fig.add_trace(go.Candlestick(
    x=df.index,
    open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
    name="Price",
    increasing_line_color="#26a69a",
    decreasing_line_color="#ef5350",
), row=1, col=1)

fig.add_trace(go.Bar(
    x=df.index, y=df["Volume"],
    name="Volume",
    marker_color="rgba(128,128,128,0.4)",
), row=2, col=1)

# ── price overlays ────────────────────────────────────────────────────────────

if show_bollinger:
    w, s = bb_params["window"], bb_params.get("num_std_dev", bb_params.get("num_std", 2))
    label = f"BB {w}/{s}"
    if strat_src and "opt" in strat_src:
        label += f" ({strat_src.split()[0]} opt)"
    bands = _get_bb(ticker, interval, w, s).iloc[-lookback_bars:]
    for col_name, color, lbl in [
        ("Upper_Band", "#ce93d8", f"{label} Upper"),
        ("Lower_Band", "#7b1fa2", f"{label} Lower"),
    ]:
        fig.add_trace(go.Scatter(
            x=df.index, y=bands[col_name],
            mode="lines", name=lbl,
            line=dict(width=1, color=color, dash="dot"), opacity=0.8,
        ), row=1, col=1)

if show_ma_double:
    ma = _get_ma_double(ticker, interval, ma_double_params["swing"], ma_double_params["long"]).iloc[-lookback_bars:]
    for col_name, color in [("MA_Swing", "#ffb74d"), ("MA_Long", "#e65100")]:
        if col_name in ma.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=ma[col_name],
                mode="lines", name=col_name,
                line=dict(width=1, color=color), opacity=0.85,
            ), row=1, col=1)

if show_ma_triple:
    ma = _get_ma_triple(ticker, interval,
                        ma_triple_params["short"], ma_triple_params["medium"],
                        ma_triple_params["long"]).iloc[-lookback_bars:]
    for col_name, color in [("MA_Short", "#4fc3f7"), ("MA_Medium", "#0288d1"), ("MA_Long", "#01579b")]:
        if col_name in ma.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=ma[col_name],
                mode="lines", name=col_name,
                line=dict(width=1, color=color), opacity=0.85,
            ), row=1, col=1)

# ── indicator subplots ────────────────────────────────────────────────────────

if show_sub:
    sub_row = 3

    if show_rsi:
        period = rsi_params["period"]
        ob     = rsi_params.get("overbought", 70)
        os_    = rsi_params.get("oversold", 30)
        label  = f"RSI ({period})" + (" ★" if chosen_name != "None" and strat_src != "base" else "")
        series = _get_rsi(ticker, interval, period).iloc[-lookback_bars:]
        fig.add_trace(go.Scatter(
            x=df.index, y=series,
            mode="lines", name=label,
            line=dict(width=1.5, color="#a5d6a7"),
        ), row=sub_row, col=1)
        fig.add_hline(y=ob,  line_dash="dot", line_color="rgba(239,83,80,0.5)",   row=sub_row, col=1)
        fig.add_hline(y=os_, line_dash="dot", line_color="rgba(38,166,154,0.5)",  row=sub_row, col=1)
        fig.add_hline(y=50,  line_dash="dot", line_color="rgba(255,255,255,0.15)",row=sub_row, col=1)
        fig.update_yaxes(title_text="RSI", range=[0, 100], row=sub_row, col=1)

    elif show_macd:
        short  = macd_params.get("short",  macd_params.get("short_window",  12))
        long_  = macd_params.get("long",   macd_params.get("long_window",   26))
        signal = macd_params.get("signal", macd_params.get("signal_window",  9))
        label  = f"MACD ({short}/{long_}/{signal})" + (" ★" if chosen_name != "None" and strat_src != "base" else "")
        out = _get_macd(ticker, interval, short, long_, signal).iloc[-lookback_bars:]
        fig.add_trace(go.Scatter(
            x=df.index, y=out["MACD"],
            mode="lines", name=label,
            line=dict(width=1.5, color="#fff176"),
        ), row=sub_row, col=1)
        if "Signal_Line" in out.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=out["Signal_Line"],
                mode="lines", name="Signal Line",
                line=dict(width=1, color="#ff8a65", dash="dot"),
            ), row=sub_row, col=1)
        fig.add_hline(y=0, line_width=1, line_color="rgba(255,255,255,0.2)", row=sub_row, col=1)
        fig.update_yaxes(title_text="MACD", row=sub_row, col=1)

    elif show_markov:
        states   = markov_params.get("states", 3)
        lookback = markov_params.get("lookback", 60)
        bull_thr = markov_params.get("bull_threshold", 0.5)
        bear_thr = markov_params.get("bear_threshold", 0.5)
        opt_star = " ★" if chosen_name != "None" and strat_src != "base" else ""
        mk = _get_markov(ticker, interval, states, lookback).iloc[-lookback_bars:]

        fig.add_trace(go.Scatter(
            x=mk.index, y=mk["bull_prob"],
            mode="lines", name=f"Bull prob{opt_star}",
            line=dict(width=1.5, color="#26a69a"),
        ), row=sub_row, col=1)
        fig.add_trace(go.Scatter(
            x=mk.index, y=mk["bear_prob"],
            mode="lines", name=f"Bear prob{opt_star}",
            line=dict(width=1.5, color="#ef5350"),
        ), row=sub_row, col=1)

        # threshold lines
        fig.add_hline(y=bull_thr, line_dash="dot",
                      line_color="rgba(38,166,154,0.5)", row=sub_row, col=1)
        fig.add_hline(y=bear_thr, line_dash="dot",
                      line_color="rgba(239,83,80,0.5)",  row=sub_row, col=1)

        # signal dots on the price chart
        buy_mask  = mk["bull_prob"] > bull_thr
        sell_mask = mk["bear_prob"] > bear_thr
        if buy_mask.any():
            buy_prices = df["Low"].reindex(mk.index[buy_mask]) * 0.985
            fig.add_trace(go.Scatter(
                x=mk.index[buy_mask], y=buy_prices,
                mode="markers", name="Markov BUY",
                marker=dict(symbol="triangle-up", size=10, color="#26a69a"),
            ), row=1, col=1)
        if sell_mask.any():
            sell_prices = df["High"].reindex(mk.index[sell_mask]) * 1.015
            fig.add_trace(go.Scatter(
                x=mk.index[sell_mask], y=sell_prices,
                mode="markers", name="Markov SELL",
                marker=dict(symbol="triangle-down", size=10, color="#ef5350"),
            ), row=1, col=1)

        fig.update_yaxes(title_text="Markov", range=[0, 1], row=sub_row, col=1)

# ── layout ────────────────────────────────────────────────────────────────────

min_p = df["Low"].min()
max_p = df["High"].max()
pad   = (max_p - min_p) * pad_pct
fig.update_yaxes(range=[min_p - pad, max_p + pad], row=1, col=1)
fig.update_yaxes(title_text="Volume", row=2, col=1, showgrid=False)
fig.update_layout(
    height=720 if show_sub else 620,
    xaxis_rangeslider_visible=False,
    margin=dict(l=0, r=0, t=30, b=0),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=11)),
)

if asset_type in ("stocks", "etfs") and interval in ("1m", "2m", "5m", "15m", "30m", "1h"):
    for r in range(1, n_rows + 1):
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], row=r, col=1)

# ── earnings overlays ─────────────────────────────────────────────────────────

if show_earnings and asset_type in ("stocks", "etfs"):
    edata = _get_earnings(ticker)
    hist  = edata.get("history", pd.DataFrame())

    for ts, row in hist.iterrows():
        d = ts.date() if hasattr(ts, "date") else ts
        surprise = row.get("surprise_pct")
        reported = row.get("reported_eps")
        estimate = row.get("eps_estimate")

        if surprise is None or pd.isna(surprise):
            color, label_color = "rgba(150,150,150,0.4)", "#aaaaaa"
            result = "?"
        elif surprise >= 0:
            color, label_color = "rgba(38,166,154,0.15)", "#26a69a"
            result = f"+{surprise:.1f}%"
        else:
            color, label_color = "rgba(239,83,80,0.15)", "#ef5350"
            result = f"{surprise:.1f}%"

        fig.add_vline(
            x=str(d), line_width=1.5,
            line_color=label_color, line_dash="dot",
        )
        est_str = f" (est {estimate:.2f})" if estimate and not pd.isna(estimate) else ""
        rep_str = f"EPS {reported:.2f}{est_str} · {result}" if reported and not pd.isna(reported) else result
        fig.add_annotation(
            x=str(d), y=1, yref="paper",
            text=rep_str, showarrow=False,
            font=dict(size=9, color=label_color),
            bgcolor="rgba(20,20,20,0.7)",
            xanchor="left", yanchor="top",
        )

    # Next earnings date
    next_date = edata.get("next_date")
    next_eps  = edata.get("next_eps_estimate")
    if next_date:
        eps_label = f"est EPS {next_eps:.2f}" if next_eps else "upcoming"
        fig.add_vline(
            x=str(next_date), line_width=2,
            line_color="#ffa726", line_dash="dash",
        )
        fig.add_annotation(
            x=str(next_date), y=0.97, yref="paper",
            text=f"Earnings · {eps_label}",
            showarrow=False,
            font=dict(size=9, color="#ffa726"),
            bgcolor="rgba(20,20,20,0.8)",
            xanchor="left", yanchor="top",
        )

# ── forward date markers (15 / 30 / 45 days) ─────────────────────────────────

if show_forward:
    today = date.today()
    for days, color in [(15, "rgba(100,181,246,0.5)"),
                        (30, "rgba(129,212,250,0.5)"),
                        (45, "rgba(179,229,252,0.5)")]:
        fwd = today + timedelta(days=days)
        fig.add_vline(x=str(fwd), line_width=1, line_color=color, line_dash="dash")
        fig.add_annotation(
            x=str(fwd), y=0.85, yref="paper",
            text=f"+{days}d", showarrow=False,
            font=dict(size=9, color=color),
            xanchor="center",
        )

st.plotly_chart(fig, use_container_width=True)

last = df.iloc[-1]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Close", f"${last['Close']:.2f}")
c2.metric("Open",  f"${last['Open']:.2f}")
c3.metric("High",  f"${last['High']:.2f}")
c4.metric("Low",   f"${last['Low']:.2f}")

if chosen_name != "None" and strat:
    with st.expander("Active strategy params"):
        st.json(strat.get("indicators", {}))
