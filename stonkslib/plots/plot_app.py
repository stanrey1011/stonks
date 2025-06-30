import streamlit as st
import pandas as pd
import plotly.graph_objs as go
import os

st.set_page_config(layout="wide")

def plot_trades(price_path, trades_path, title="Backtest Trades"):
    price = pd.read_csv(price_path, index_col=0, parse_dates=True)
    trades = pd.read_csv(trades_path)
    trades['date'] = pd.to_datetime(trades['date'])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=price.index, y=price['Close'],
        mode='lines', name='Close Price',
        line=dict(color='blue')
    ))
    buy_trades = trades[trades['action'].str.upper() == "BUY"]
    fig.add_trace(go.Scatter(
        x=buy_trades['date'],
        y=price.loc[buy_trades['date'], 'Close'],
        mode='markers',
        marker=dict(symbol='triangle-up', size=10, color='green'),
        name='Buy',
        text=[f"BUY<br>Date: {d.strftime('%Y-%m-%d')}<br>Price: {p:.2f}" for d, p in zip(buy_trades['date'], buy_trades['price'])]
    ))
    sell_trades = trades[trades['action'].str.upper().str.startswith('SELL')]
    fig.add_trace(go.Scatter(
        x=sell_trades['date'],
        y=price.loc[sell_trades['date'], 'Close'],
        mode='markers',
        marker=dict(symbol='triangle-down', size=10, color='red'),
        name='Sell',
        text=[f"SELL<br>Date: {d.strftime('%Y-%m-%d')}<br>Price: {p:.2f}" for d, p in zip(sell_trades['date'], sell_trades['price'])]
    ))

    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Price",
        hovermode="closest",
        legend=dict(orientation="h", x=0, y=1.15)
    )
    st.plotly_chart(fig, use_container_width=True)

# --- Discover tickers and intervals dynamically ---
data_root = "data/ticker_data/clean"
intervals = sorted(os.listdir(data_root))
tickers = sorted({f.replace(".csv", "") for interval in intervals for f in os.listdir(os.path.join(data_root, interval)) if f.endswith(".csv")})

# --- Discover pattern types dynamically ---
pattern_root = "data/analysis/backtests/patterns"
pattern_types = []
if os.path.exists(pattern_root):
    pattern_types = [name for name in os.listdir(pattern_root) if os.path.isdir(os.path.join(pattern_root, name))]
pattern_types = sorted(pattern_types)

# Add 'indicators' as first option
result_types = ["indicators"] + pattern_types

st.sidebar.title("Stonks Backtest Explorer")
ticker = st.sidebar.selectbox("Ticker", tickers)
interval = st.sidebar.selectbox("Interval", intervals)
result_type = st.sidebar.selectbox("Backtest Type", result_types)

# --- Path selection logic ---
if result_type == "indicators":
    trades_path = f"data/analysis/backtests/indicators/{ticker}_{interval}_results.csv"
else:
    trades_path = f"data/analysis/backtests/patterns/{result_type}/{ticker}/{interval}.csv"

price_path = f"data/ticker_data/clean/{interval}/{ticker}.csv"

if os.path.exists(price_path) and os.path.exists(trades_path):
    st.success(f"Loaded data for {ticker} ({interval}), type: {result_type}")
    plot_trades(price_path, trades_path, title=f"{ticker} {interval} {result_type} Trades")
    with st.expander("Show trade table"):
        trades = pd.read_csv(trades_path)
        st.dataframe(trades)
else:
    st.warning(f"No data for {ticker} ({interval}) — type: {result_type}.")
