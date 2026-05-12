import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st
import pandas as pd
import json

from stonkslib.dash.common import load_watchlist, flat_tickers, STRATEGY_DIR, BACKTEST_DIR

st.set_page_config(page_title="Backtest — Stonks", layout="wide")
st.title("Backtest")

wl = load_watchlist()
tickers = flat_tickers(wl)
if not tickers:
    st.warning("No tickers in watchlist.")
    st.stop()

col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    ticker = st.selectbox("Ticker", tickers)
with col2:
    interval = st.selectbox("Interval", ["1d", "1wk"])
with col3:
    st.write("")
    st.write("")
    run = st.button("Run Backtest", type="primary", use_container_width=True)


def _load_existing(ticker, interval):
    result_dir = BACKTEST_DIR / ticker / interval
    if not result_dir.exists():
        return []
    rows = []
    for mf in sorted(result_dir.glob("*_metrics.json")):
        with open(mf) as f:
            rows.append(json.load(f))
    return sorted(rows, key=lambda r: r["net_pnl"], reverse=True)


def _show_results(results):
    if not results:
        return
    df = pd.DataFrame(results)[["strategy", "net_pnl", "win_rate", "trades", "final_cash"]]
    df.columns = ["Strategy", "Net P&L", "Win Rate", "Trades", "Final Cash"]
    df.insert(0, "", ["★" if i == 0 else "" for i in range(len(df))])
    df["Net P&L"]    = df["Net P&L"].map(lambda x: f"${x:,.2f}")
    df["Win Rate"]   = df["Win Rate"].map("{:.1%}".format)
    df["Final Cash"] = df["Final Cash"].map(lambda x: f"${x:,.2f}")
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption("Switch to the **Trades** page to see entry/exit prices for any strategy.")


if run:
    from stonkslib.backtest.strategy import run_strategy_backtest, load_strategy

    strategy_paths = list(STRATEGY_DIR.glob("*.yaml"))
    results = []
    progress = st.progress(0, text="Running backtest...")
    for i, path in enumerate(strategy_paths):
        opt_path = STRATEGY_DIR / "optimized" / f"{path.stem}_optimized.yaml"
        active = opt_path if opt_path.exists() else path
        strat = load_strategy(active)
        progress.progress((i + 1) / len(strategy_paths), text=f"Running {strat.get('name', path.stem)}...")
        m = run_strategy_backtest(ticker, interval, strat)
        if m:
            results.append(m)
    progress.empty()
    results.sort(key=lambda r: r["net_pnl"], reverse=True)
    st.success(f"Backtest complete — {len(results)} strategies.")
    _show_results(results)
else:
    existing = _load_existing(ticker, interval)
    if existing:
        st.caption(f"Showing saved results for **{ticker}** ({interval}). Click **Run Backtest** to refresh.")
        _show_results(existing)
    else:
        st.caption(f"No saved results for **{ticker}** ({interval}). Click **Run Backtest**.")
