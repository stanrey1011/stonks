import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from stonkslib.dash.common import load_watchlist, flat_tickers, load_ticker_data
from stonkslib.indicators.markov import markov_signals, markov_forecast

st.set_page_config(page_title="Markov Forecast — Stonks", layout="wide")
st.title("Markov Forecast")
st.caption(
    "Short-horizon (1–5 day) state forecast from a discrete Markov chain on log "
    "returns. The forecast fan decaying toward the dashed stationary lines means "
    "the chain has little multi-day memory for this ticker — read a persistent "
    "skew as an edge, a flat fan as noise."
)

wl = load_watchlist()
tickers = flat_tickers(wl)
if not tickers:
    st.warning("No tickers in watchlist.")
    st.stop()

with st.sidebar:
    ticker = st.selectbox("Ticker", tickers, key="mk_ticker")
    interval = st.selectbox("Interval", ["1d", "1wk"], key="mk_interval")
    states = st.slider("States", 2, 5, 3, key="mk_states",
                       help="Number of return regimes (quantile bins)")
    lookback = st.slider("Lookback", 20, 120, 60, step=10, key="mk_lookback",
                         help="Rolling window of bars used to estimate transitions")
    days_ahead = st.slider("Days ahead", 1, 5, 5, key="mk_days")


@st.cache_data(ttl=3600, show_spinner=False)
def _history(ticker: str, interval: str, states: int, lookback: int) -> pd.DataFrame | None:
    df = load_ticker_data(ticker, interval)
    if df is None or df.empty:
        return None
    tail = df.tail(400).copy()
    mk = markov_signals(tail, states=states, lookback=lookback)
    return tail.join(mk)


@st.cache_data(ttl=3600, show_spinner=False)
def _forecast(ticker: str, interval: str, states: int, lookback: int, days_ahead: int) -> dict | None:
    df = load_ticker_data(ticker, interval)
    if df is None or df.empty:
        return None
    return markov_forecast(df.copy(), states=states, lookback=lookback, days_ahead=days_ahead)


hist = _history(ticker, interval, states, lookback)
fc = _forecast(ticker, interval, states, lookback, days_ahead)

if hist is None or fc is None or fc.get("current_state") is None:
    st.warning(f"Not enough data for {ticker} ({interval}) at lookback {lookback}. "
               "Try a smaller lookback or run the pipeline for this ticker.")
    st.stop()

cur = fc["current_state"]
stationary = fc["stationary"]
horizons = fc["horizons"]

if cur >= states - 1:
    regime, regime_color = "BULLISH", "🟢"
elif cur == 0:
    regime, regime_color = "BEARISH", "🔴"
else:
    regime, regime_color = "NEUTRAL", "🟡"

# where does the forecast collapse to the stationary distribution?
flat_at = next((h["h"] for h in horizons if h["dist_to_stationary"] < 0.03), None)
memory = f"flattens by D{flat_at}" if flat_at else "persistent"
d1 = horizons[0]

# ── headline metrics ────────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("Current state", f"{cur} / {states - 1}", regime_color + " " + regime)
m2.metric("P(→bull) D1", f"{d1['bull_prob']:.0%}")
m3.metric("P(→bear) D1", f"{d1['bear_prob']:.0%}")
m4.metric("Memory", memory, help="Horizon at which the forecast collapses to the stationary distribution")

st.caption(
    "Stationary distribution: "
    + "  ".join(f"S{i}={p:.0%}" for i, p in enumerate(stationary))
    + " — the long-run regime mix the chain drifts to with no memory."
)

# ── price + historical state probability ────────────────────────────────────
fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.62, 0.38],
                    vertical_spacing=0.04,
                    subplot_titles=(f"{ticker} ({interval})", "Markov P(→bull) / P(→bear)"))

fig.add_trace(go.Candlestick(
    x=hist.index, open=hist["Open"], high=hist["High"],
    low=hist["Low"], close=hist["Close"], name="Price",
    increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
), row=1, col=1)

fig.add_trace(go.Scatter(x=hist.index, y=hist["bull_prob"], name="P(→bull)",
                         line=dict(color="#26a69a", width=1.2)), row=2, col=1)
fig.add_trace(go.Scatter(x=hist.index, y=hist["bear_prob"], name="P(→bear)",
                         line=dict(color="#ef5350", width=1.2)), row=2, col=1)
fig.update_layout(height=520, margin=dict(l=0, r=0, t=30, b=0),
                  xaxis_rangeslider_visible=False,
                  legend=dict(orientation="h", y=1.08))
fig.update_yaxes(range=[0, 1], row=2, col=1)
st.plotly_chart(fig, use_container_width=True)

# ── 1–N day forecast fan ────────────────────────────────────────────────────
st.subheader("1–%d day forecast fan" % days_ahead)
xs = [f"D{h['h']}" for h in horizons]
fan = go.Figure()
fan.add_trace(go.Scatter(x=xs, y=[h["bull_prob"] for h in horizons], name="P(→bull)",
                         mode="lines+markers", line=dict(color="#26a69a", width=2)))
fan.add_trace(go.Scatter(x=xs, y=[h["bear_prob"] for h in horizons], name="P(→bear)",
                         mode="lines+markers", line=dict(color="#ef5350", width=2)))
fan.add_hline(y=stationary[states - 1], line_dash="dash", line_color="#26a69a",
              annotation_text="bull stationary", annotation_position="right")
fan.add_hline(y=stationary[0], line_dash="dash", line_color="#ef5350",
              annotation_text="bear stationary", annotation_position="right")
fan.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0),
                  yaxis=dict(range=[0, 1], title="probability"),
                  legend=dict(orientation="h", y=1.15))
st.plotly_chart(fan, use_container_width=True)
st.caption("Lines converging to the dashed stationary levels = the chain forgets the "
           "current state. Sustained skew above/below = genuine short-term persistence.")

# ── forecast table ──────────────────────────────────────────────────────────
tbl = pd.DataFrame([{
    "Horizon": f"D{h['h']}",
    "P(→bull)": round(h["bull_prob"] * 100, 1),
    "P(→bear)": round(h["bear_prob"] * 100, 1),
    "Dist to stationary": h["dist_to_stationary"],
    "Confidence": h["confidence"],
} for h in horizons])
st.dataframe(
    tbl,
    column_config={
        "P(→bull)": st.column_config.NumberColumn("P(→bull)", format="%.0f%%"),
        "P(→bear)": st.column_config.NumberColumn("P(→bear)", format="%.0f%%"),
        "Dist to stationary": st.column_config.NumberColumn(
            "Dist to stationary", format="%.3f",
            help="Total-variation distance from the stationary distribution (0 = no edge left)"),
    },
    use_container_width=True, hide_index=True,
)
