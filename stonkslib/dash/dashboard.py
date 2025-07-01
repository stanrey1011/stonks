import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
from stonkslib.dash.data import load_tickers, get_asset_type, load_and_filter_df
from stonkslib.dash.overlays import overlay_trace

st.title("Stonks Quant Chart Dashboard — With Indicator Layers, Volume & Scaling")

tickers, all_tickers = load_tickers("tickers.yaml")

# --- Sidebar controls ---
ticker = st.sidebar.selectbox("Select Ticker", all_tickers)
interval = st.sidebar.selectbox("Interval", ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"])

show_close_line = st.sidebar.checkbox("Show Close Line", value=False)
show_bollinger = st.sidebar.checkbox("Show Bollinger Bands", value=False)
show_ma_double = st.sidebar.checkbox("Show Double Moving Average", value=False)
show_ma_triple = st.sidebar.checkbox("Show Triple Moving Average", value=False)
show_macd = st.sidebar.checkbox("Show MACD", value=False)
show_rsi = st.sidebar.checkbox("Show RSI", value=False)

pad_pct = st.sidebar.slider("Vertical Padding (%)", 1, 30, 10) / 100

asset_type = get_asset_type(ticker, tickers)
DATA_PATH = f"data/ticker_data/clean/{interval}/{ticker}.csv"
if not Path(DATA_PATH).exists():
    st.warning(f"No data found for {ticker} ({interval})")
    st.stop()
df = load_and_filter_df(DATA_PATH, interval, asset_type)
x_for_chart = df.index

fig = make_subplots(
    rows=2, cols=1,
    shared_xaxes=True,
    row_heights=[0.7, 0.3],
    vertical_spacing=0.03,
    subplot_titles=("Price", "Volume"),
)
fig.add_trace(go.Candlestick(
    x=x_for_chart,
    open=df['Open'],
    high=df['High'],
    low=df['Low'],
    close=df['Close'],
    name="Price"
), row=1, col=1)
fig.add_trace(go.Bar(
    x=x_for_chart,
    y=df["Volume"],
    name="Volume",
    marker_color="gray",
    opacity=0.6,
), row=2, col=1)

signals_path = Path(f"data/analysis/signals/{ticker}/{interval}")
if show_close_line:
    fig.add_trace(go.Scatter(
        x=x_for_chart,
        y=df["Close"],
        mode="lines",
        name="Close",
        line=dict(width=1)
    ), row=1, col=1)
if show_bollinger:
    overlay_trace(fig, signals_path / "bollinger.csv", df, interval, dash="dot")
if show_ma_double:
    overlay_trace(fig, signals_path / "ma_double.csv", df, interval)
if show_ma_triple:
    overlay_trace(fig, signals_path / "ma_triple.csv", df, interval)
if show_macd:
    overlay_trace(fig, signals_path / "macd.csv", df, interval, name_fmt="MACD ({col})")
if show_rsi:
    overlay_trace(fig, signals_path / "rsi.csv", df, interval, name_fmt="RSI ({col})")

min_price = df['Low'].min()
max_price = df['High'].max()
padding = (max_price - min_price) * pad_pct
fig.update_yaxes(
    range=[min_price - padding, max_price + padding],
    autorange=False,
    row=1, col=1,
)
fig.update_yaxes(title_text="Volume", row=2, col=1, showgrid=False)

if asset_type in ['stocks', 'etfs'] and interval in ["1m","2m","5m","15m","30m","1h"]:
    for row in [1, 2]:
        fig.update_xaxes(
            rangebreaks=[
                dict(bounds=["sat", "mon"]),
            ],
            range=[df.index.min(), df.index.max()],
            tickformatstops=[
                dict(dtickrange=[None, 1000 * 60 * 60 * 24], value="%Y-%m-%d %H:%M"),
                dict(dtickrange=[1000 * 60 * 60 * 24, None], value="%Y-%m-%d"),
            ],
            row=row, col=1
        )

st.markdown(f"### {ticker} — {interval} Chart (with Volume)")
st.plotly_chart(fig, use_container_width=True)

# --- Debug Panel ---
with st.expander("Show raw data (debug)", expanded=False):
    st.write(f"Data shape: {df.shape}")
    st.write(f"Index dtype: {df.index.dtype}")
    st.write(f"First index: {df.index[0]}  Last index: {df.index[-1]}")
    st.write(f"Index timezone: {getattr(df.index, 'tz', None)}")
    if asset_type in ['stocks', 'etfs'] and interval in ["1m", "2m", "5m", "15m", "30m", "1h"]:
        st.write("Filtered index unique hours:", sorted(set(df.index.hour)))
        st.write("Filtered index unique minutes:", sorted(set(df.index.minute)))
        st.write("Filtered index unique days of week:", sorted(set(df.index.dayofweek)))
        st.write("Filtered index sample:", df.index[:10])
    st.write(df.head(5))
    st.write(df.tail(5))
