import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st
import subprocess

from stonkslib.dash.common import (
    load_watchlist, save_watchlist, STONKS_BIN, VALID_CATEGORIES,
)

st.set_page_config(page_title="Watchlist — Stonks", layout="wide")
st.title("Watchlist")

wl = load_watchlist()

# --- Current watchlist ---
any_tickers = any(items for items in wl.values() if items)
if not any_tickers:
    st.info("Watchlist is empty. Add tickers below.")
else:
    for cat, items in wl.items():
        if not items:
            continue
        st.subheader(cat.capitalize())
        cols = st.columns(8)
        for i, ticker in enumerate(list(items)):
            with cols[i % 8]:
                if st.button(f"✕ {ticker}", key=f"rm_{ticker}", help=f"Remove {ticker}"):
                    wl2 = load_watchlist()
                    for c, lst in wl2.items():
                        if lst and ticker in lst:
                            lst.remove(ticker)
                    save_watchlist(wl2)
                    st.success(f"Removed {ticker}")
                    st.rerun()

st.divider()

# --- Add ticker ---
st.subheader("Add Ticker")
col1, col2, col3 = st.columns([3, 2, 2])
with col1:
    new_ticker = st.text_input("Symbol", placeholder="e.g. AMD or SOL-USD").strip().upper()
with col2:
    new_cat = st.selectbox("Category", VALID_CATEGORIES)
with col3:
    st.write("")
    st.write("")
    add = st.button("Add + Fetch Data", type="primary", use_container_width=True)

if add:
    if not new_ticker:
        st.warning("Enter a ticker symbol.")
    else:
        wl2 = load_watchlist()
        wl2.setdefault(new_cat, [])
        if new_ticker in wl2.get(new_cat, []):
            st.warning(f"{new_ticker} is already in {new_cat}.")
        else:
            wl2[new_cat].append(new_ticker)
            save_watchlist(wl2)
            with st.spinner(f"Running pipeline for {new_ticker} (~30s)..."):
                result = subprocess.run(
                    [str(STONKS_BIN), "pipeline", new_ticker],
                    capture_output=True, text=True, timeout=300,
                )
            if result.returncode == 0:
                st.success(f"Added **{new_ticker}** to {new_cat} and fetched data.")
            else:
                err = result.stderr.strip() or "unknown error"
                st.error(f"Added **{new_ticker}** but pipeline failed: {err}")
            st.rerun()
