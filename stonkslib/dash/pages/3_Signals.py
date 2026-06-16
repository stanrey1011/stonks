import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st
import pandas as pd
import yaml

from stonkslib.dash.common import load_watchlist, flat_tickers, STRATEGY_DIR
from stonkslib.utils.active_strategies import all_strategy_paths, active_strategy_names

st.set_page_config(page_title="Signals — Stonks", layout="wide")
st.title("Signals")
st.caption("Runs a live signal scan on the latest bar for any ticker and strategy. Shows BUY and SELL signals with the reason each fired. Optimized strategy params are used automatically when available. Use this to check a specific ticker on demand without waiting for the daily alert.")

wl = load_watchlist()
tickers = flat_tickers(wl)
if not tickers:
    st.warning("No tickers in watchlist.")
    st.stop()

_all_stems = [p.stem for p in all_strategy_paths()]
_active = [s for s in active_strategy_names() if s in _all_stems] or _all_stems
chosen_stems = st.multiselect(
    "Strategies to scan", _all_stems, default=_active, key="sig_strategies",
    help="Defaults to the curated active set (config.yaml: active_strategies). Add more to widen the scan.",
)

col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    target = st.selectbox("Ticker", ["All watchlist"] + tickers, key="sig_target")
with col2:
    interval = st.selectbox("Interval", ["1d", "1wk"], key="sig_interval")
with col3:
    st.write("")
    st.write("")
    run = st.button("Scan now", type="primary", use_container_width=True)

if run:
    from stonkslib.alerts.signals import check_signals

    scan_tickers = tickers if target == "All watchlist" else [target]
    strategy_paths = [STRATEGY_DIR / f"{s}.yaml" for s in chosen_stems] or all_strategy_paths()
    all_signals = []

    progress = st.progress(0, text="Scanning...")
    for i, path in enumerate(strategy_paths):
        opt_path = STRATEGY_DIR / "optimized" / f"{path.stem}_optimized.yaml"
        active = opt_path if opt_path.exists() else path
        with open(active) as f:
            strat = yaml.safe_load(f)
        for t in scan_tickers:
            sigs = check_signals(t, interval, strat)
            if sigs:
                for s in sigs:
                    s["strategy"] = strat.get("name", path.stem)
                all_signals.extend(sigs)
        progress.progress((i + 1) / len(strategy_paths), text=f"Scanning {path.stem}...")
    progress.empty()

    if not all_signals:
        st.info(f"No signals on the latest **{interval}** bar.")
    else:
        buys  = [s for s in all_signals if s["type"] == "BUY"]
        sells = [s for s in all_signals if s["type"] == "SELL"]

        if buys:
            st.subheader(f"🟢 BUY — {len(buys)} signal(s)")
            df_b = pd.DataFrame(buys)[["ticker", "close", "reason", "strategy", "date"]]
            df_b.columns = ["Ticker", "Price", "Reason", "Strategy", "Date"]
            df_b["Date"] = df_b["Date"].astype(str).str[:10]
            st.dataframe(df_b, use_container_width=True, hide_index=True)

        if sells:
            st.subheader(f"🔴 SELL — {len(sells)} signal(s)")
            df_s = pd.DataFrame(sells)[["ticker", "close", "reason", "strategy", "date"]]
            df_s.columns = ["Ticker", "Price", "Reason", "Strategy", "Date"]
            df_s["Date"] = df_s["Date"].astype(str).str[:10]
            st.dataframe(df_s, use_container_width=True, hide_index=True)
else:
    st.caption("Select a ticker and interval, then click **Scan now**.")
