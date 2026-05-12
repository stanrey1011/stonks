import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from stonkslib.dash.common import (
    load_watchlist, flat_tickers, load_ticker_data,
    SIGNALS_DIR, INTERVALS,
)
from stonkslib.dash.overlays import overlay_trace

st.set_page_config(page_title="Chart — Stonks", layout="wide")
st.title("Chart")

wl = load_watchlist()
tickers = flat_tickers(wl)
if not tickers:
    st.warning("No tickers in watchlist. Add some on the Watchlist page.")
    st.stop()

col1, col2 = st.columns([3, 1])
with col1:
    ticker = st.selectbox("Ticker", tickers)
with col2:
    interval = st.selectbox("Interval", INTERVALS)

with st.sidebar:
    st.subheader("Overlays")
    show_bollinger = st.checkbox("Bollinger Bands")
    show_ma_double = st.checkbox("Double MA (20/50 EMA)")
    show_ma_triple = st.checkbox("Triple MA (9/21/50 EMA)")
    show_macd     = st.checkbox("MACD")
    show_rsi      = st.checkbox("RSI (14)")
    st.divider()
    pad_pct = st.slider("Y-axis padding %", 1, 20, 5) / 100

df = load_ticker_data(ticker, interval)
if df is None:
    st.error(f"No data for **{ticker}** ({interval}). Run: `stonks pipeline {ticker}`")
    st.stop()

asset_type = next((cat for cat, items in wl.items() if items and ticker in items), "unknown")

fig = make_subplots(
    rows=2, cols=1,
    shared_xaxes=True,
    row_heights=[0.75, 0.25],
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

signals_path = SIGNALS_DIR / ticker / interval
if show_bollinger:
    overlay_trace(fig, signals_path / "bollinger.csv", df, interval, dash="dot")
if show_ma_double:
    overlay_trace(fig, signals_path / "ma_double.csv", df, interval)
if show_ma_triple:
    overlay_trace(fig, signals_path / "ma_triple.csv", df, interval)
if show_macd:
    overlay_trace(fig, signals_path / "macd.csv", df, interval, name_fmt="MACD ({col})")
if show_rsi:
    overlay_trace(fig, signals_path / "rsi_14.csv", df, interval, name_fmt="RSI ({col})")

min_p = df["Low"].min()
max_p = df["High"].max()
pad   = (max_p - min_p) * pad_pct
fig.update_yaxes(range=[min_p - pad, max_p + pad], row=1, col=1)
fig.update_yaxes(title_text="Volume", row=2, col=1, showgrid=False)
fig.update_layout(
    height=660,
    xaxis_rangeslider_visible=False,
    margin=dict(l=0, r=0, t=30, b=0),
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)

if asset_type in ("stocks", "etfs") and interval in ("1m", "2m", "5m", "15m", "30m", "1h"):
    for r in [1, 2]:
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], row=r, col=1)

st.plotly_chart(fig, use_container_width=True)

last = df.iloc[-1]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Close",  f"${last['Close']:.2f}")
c2.metric("Open",   f"${last['Open']:.2f}")
c3.metric("High",   f"${last['High']:.2f}")
c4.metric("Low",    f"${last['Low']:.2f}")
