import streamlit as st
import yaml
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

st.title("Stonks Quant Chart Dashboard — With Indicator Layers & Scaling")

# --- Load tickers from YAML ---
with open("tickers.yaml", "r") as f:
    tickers = yaml.safe_load(f)
all_tickers = []
for cat, tlist in tickers.items():
    all_tickers.extend(tlist)

# --- Sidebar controls ---
ticker = st.sidebar.selectbox("Select Ticker", all_tickers)
interval = st.sidebar.selectbox("Interval", ["1m","2m","5m","15m","30m","1h","1d","1wk"])

show_close_line = st.sidebar.checkbox("Show Close Line", value=False)
show_bollinger = st.sidebar.checkbox("Show Bollinger Bands", value=False)
show_ma_double = st.sidebar.checkbox("Show Double Moving Average", value=False)
show_ma_triple = st.sidebar.checkbox("Show Triple Moving Average", value=False)

# --- Candle scaling control ---
pad_pct = st.sidebar.slider("Vertical Padding (%)", 1, 30, 10) / 100

# --- Load cleaned OHLCV data ---
DATA_PATH = f"data/ticker_data/clean/{interval}/{ticker}.csv"
if not Path(DATA_PATH).exists():
    st.warning(f"No data found for {ticker} ({interval})")
    st.stop()
df = pd.read_csv(DATA_PATH, parse_dates=True, index_col=0)

# --- Main Chart: Candle ---
fig = go.Figure()
fig.add_trace(go.Candlestick(
    x=df.index,
    open=df['Open'],
    high=df['High'],
    low=df['Low'],
    close=df['Close'],
    name="Price"
))

# --- Optional overlays ---
if show_close_line:
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df["Close"],
        mode="lines",
        name="Close",
        line=dict(width=1)
    ))

signals_path = Path(f"data/analysis/signals/{ticker}/{interval}")

if show_bollinger:
    bb_path = signals_path / "bollinger.csv"
    if bb_path.exists():
        bb = pd.read_csv(bb_path, index_col=0, parse_dates=True)
        bb = bb.reindex(df.index)
#        st.write("Bollinger columns:", list(bb.columns))
        for col in bb.columns:
#            st.write(f"{col} - Non-NaN count: {bb[col].notna().sum()}")
            if bb[col].notna().sum() > 0:
                fig.add_trace(go.Scatter(
                    x=bb.index,
                    y=bb[col],
                    mode="lines",
                    name=col,
                    line=dict(width=1, dash='dot')
                ))
    else:
        st.warning("No bollinger.csv found for this ticker/interval.")


if show_ma_double:
    ma_double_path = signals_path / "ma_double.csv"
    if ma_double_path.exists():
        ma_double = pd.read_csv(ma_double_path, index_col=0, parse_dates=True)
        for col in ma_double.columns:
            fig.add_trace(go.Scatter(
                x=ma_double.index, y=ma_double[col], mode="lines", name=col, line=dict(width=1)
            ))

if show_ma_triple:
    ma_triple_path = signals_path / "ma_triple.csv"
    if ma_triple_path.exists():
        ma_triple = pd.read_csv(ma_triple_path, index_col=0, parse_dates=True)
        for col in ma_triple.columns:
            fig.add_trace(go.Scatter(
                x=ma_triple.index, y=ma_triple[col], mode="lines", name=col, line=dict(width=1)
            ))

# --- Vertical candle scaling ---
min_price = df['Low'].min()
max_price = df['High'].max()
padding = (max_price - min_price) * pad_pct
fig.update_yaxes(
    range=[min_price - padding, max_price + padding],
    autorange=False
)

# --- Chart title (Streamlit only, not inside chart) ---
st.markdown(f"### {ticker} — {interval} Chart")

st.plotly_chart(fig, use_container_width=True)

# --- Debug Panel ---
with st.expander("Show raw data (debug)", expanded=False):
    st.write(f"Data shape: {df.shape}")
    st.write(f"Index dtype: {df.index.dtype}")
    st.write(f"First index: {df.index[0]}  Last index: {df.index[-1]}")
    st.write(df.head(5))
    st.write(df.tail(5))
