import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

_PAGES_DIR = Path(__file__).resolve().parent / "pages"

pg = st.navigation({
    "Home": [
        st.Page(_PAGES_DIR / "0_Home.py",         title="Home",        icon="🏠"),
        st.Page(_PAGES_DIR / "6_Watchlist.py",    title="Watchlist",   icon="⭐"),
    ],
    "Analysis": [
        st.Page(_PAGES_DIR / "9_Alerts.py",       title="Alerts",      icon="🚨"),
        st.Page(_PAGES_DIR / "10_News.py",        title="News",        icon="📰"),
        st.Page(_PAGES_DIR / "2_Confluence.py",   title="Confluence",  icon="📊"),
        st.Page(_PAGES_DIR / "1_Chart.py",        title="Chart",       icon="📈"),
        st.Page(_PAGES_DIR / "3_Signals.py",      title="Signals",     icon="🔔"),
    ],
    "Portfolio": [
        st.Page(_PAGES_DIR / "8_Alpaca.py",       title="Alpaca",      icon="🦙"),
        st.Page(_PAGES_DIR / "12_Robinhood.py",   title="Robinhood",   icon="🪶"),
        # 13_IBKR.py next
    ],
    "Trading": [
        st.Page(_PAGES_DIR / "4_Backtest.py",     title="Backtest",    icon="🧪"),
        st.Page(_PAGES_DIR / "5_Trades.py",       title="Trades",      icon="📋"),
    ],
    "Configuration": [
        st.Page(_PAGES_DIR / "7_Pipeline.py",     title="Pipeline",    icon="⚙️"),
    ],
    "AI": [
        st.Page(_PAGES_DIR / "11_Chat.py",        title="Chat",        icon="💬"),
    ],
})

pg.run()
