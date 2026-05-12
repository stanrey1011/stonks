import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

st.set_page_config(page_title="Stonks", page_icon="📈", layout="wide")
st.title("📈 Stonks Dashboard")
st.markdown("""
Use the sidebar to navigate between pages.

| Page | Description |
|---|---|
| **Chart** | Candlestick chart with indicator overlays |
| **Signals** | Scan for BUY/SELL signals across strategies |
| **Backtest** | Run strategies and compare performance |
| **Trades** | View entry/exit prices for a strategy |
| **Watchlist** | Add and remove tickers |
""")
