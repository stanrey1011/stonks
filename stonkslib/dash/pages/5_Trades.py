import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st
import pandas as pd

from stonkslib.dash.common import load_watchlist, flat_tickers, BACKTEST_DIR

st.set_page_config(page_title="Trades — Stonks", layout="wide")
st.title("Trades")
st.caption("Shows the individual entry and exit trades from a saved backtest — date, price, size, P&L, and the reason each trade fired. Use this to verify that the strategy is entering and exiting at sensible points, and cross-reference with the Chart page to see the trades visually.")

wl = load_watchlist()
tickers = flat_tickers(wl)
if not tickers:
    st.warning("No tickers in watchlist.")
    st.stop()

col1, col2 = st.columns([3, 1])
with col1:
    ticker = st.selectbox("Ticker", tickers, key="trades_ticker")
with col2:
    interval = st.selectbox("Interval", ["1d", "1wk"], key="trades_interval")

result_dir = BACKTEST_DIR / ticker / interval
csvs = sorted(result_dir.glob("*.csv")) if result_dir.exists() else []

if not csvs:
    st.info(f"No trade logs for **{ticker}** ({interval}). Run a backtest first.")
    st.stop()

strategy_map = {c.stem.replace("_", " ").title(): c for c in csvs}
strategy = st.selectbox("Strategy", list(strategy_map.keys()))

try:
    df = pd.read_csv(strategy_map[strategy])
except pd.errors.EmptyDataError:
    st.info("No trades recorded for this strategy — the backtest ran but had no entries.")
    st.stop()
if df.empty:
    st.info("No trades recorded for this strategy.")
    st.stop()

buys  = df[df["action"] == "BUY"].reset_index(drop=True)
sells = df[df["action"].isin(["SELL", "SELL_END"])].reset_index(drop=True)

rows = []
for i in range(len(buys)):
    b = buys.iloc[i]
    row = {
        "#":          i + 1,
        "Buy Date":   str(b["date"])[:10],
        "Buy Price":  float(b["price"]),
        "Sell Date":  None,
        "Sell Price": None,
        "P&L":        None,
        "Result":     "Open",
        "Reason":     b.get("reason", ""),
    }
    if i < len(sells):
        s = sells.iloc[i]
        pnl = float(s.get("pnl", 0))
        row["Sell Date"]  = str(s["date"])[:10]
        row["Sell Price"] = float(s["price"])
        row["P&L"]        = pnl
        row["Result"]     = "Win" if pnl >= 0 else "Loss"
    rows.append(row)

trades_df = pd.DataFrame(rows)
closed = trades_df[trades_df["Result"].isin(["Win", "Loss"])]
total_pnl = closed["P&L"].sum() if not closed.empty else 0
wins      = len(closed[closed["Result"] == "Win"])
losses    = len(closed[closed["Result"] == "Loss"])
win_rate  = wins / len(closed) if len(closed) > 0 else 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Trades", len(buys))
c2.metric("Closed",       len(closed))
c3.metric("Wins",         wins)
c4.metric("Losses",       losses)
c5.metric("Total P&L",    f"${total_pnl:,.2f}", delta_color="normal")

st.divider()

# Format for display
disp = trades_df.copy()
disp["Buy Price"]  = disp["Buy Price"].map("${:.2f}".format)
disp["Sell Price"] = disp["Sell Price"].apply(lambda x: f"${x:.2f}" if x is not None else "—")
disp["P&L"] = disp["P&L"].apply(
    lambda x: (f"+${x:.2f}" if x >= 0 else f"-${abs(x):.2f}") if x is not None else "—"
)
disp["Sell Date"] = disp["Sell Date"].fillna("open")

st.dataframe(disp, use_container_width=True, hide_index=True)
