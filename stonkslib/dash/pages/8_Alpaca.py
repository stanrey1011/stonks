import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from stonkslib.dash.common import (
    load_watchlist, flat_tickers,
    render_account_metrics, render_positions_table, render_orders_table,
)

st.set_page_config(page_title="Alpaca — Stonks", layout="wide")
st.title("Alpaca")

try:
    from stonkslib.broker.alpaca import (
        get_account, get_positions, get_orders,
        get_portfolio_history, get_watchlist, sync_watchlist,
        is_live_configured,
    )
    _broker_available = True
except ImportError:
    _broker_available = False

if not _broker_available:
    st.error("alpaca-py not installed. Run: `pip install alpaca-py`")
    st.stop()


# ── account selector ──────────────────────────────────────────────────────────

live_configured = is_live_configured()

c_sel, c_ref = st.columns([4, 1])
with c_sel:
    options = ["Paper"]
    if live_configured:
        options.append("Live")
    account_type = st.radio(
        "Account", options, horizontal=True, key="portfolio_account",
        label_visibility="collapsed",
    )
with c_ref:
    st.write("")
    if st.button("🔄 Refresh", key="portfolio_refresh"):
        st.cache_data.clear()
        st.rerun()

live = account_type == "Live"

if not live_configured:
    st.caption("Live account not configured — add `ALPACA_LIVE_API_KEY` and `ALPACA_LIVE_SECRET_KEY` to `.env`")

st.divider()


# ── cached loaders ────────────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def _get_account(live: bool) -> dict:
    return get_account(live=live)

@st.cache_data(ttl=60, show_spinner=False)
def _get_positions(live: bool) -> pd.DataFrame:
    return get_positions(live=live)

@st.cache_data(ttl=60, show_spinner=False)
def _get_orders(live: bool) -> pd.DataFrame:
    return get_orders(live=live, limit=25)

@st.cache_data(ttl=300, show_spinner=False)
def _get_history(live: bool, period: str) -> pd.DataFrame:
    return get_portfolio_history(live=live, period=period, timeframe="1D")

@st.cache_data(ttl=300, show_spinner=False)
def _get_alpaca_watchlist(live: bool) -> list[str]:
    return get_watchlist(live=live)


# ── tabs ──────────────────────────────────────────────────────────────────────

tab_overview, tab_positions, tab_orders, tab_sync = st.tabs([
    "Overview", "Positions", "Orders", "Watchlist Sync"
])


# ── overview tab ──────────────────────────────────────────────────────────────

with tab_overview:
    try:
        acct = _get_account(live)
        render_account_metrics(acct)

        st.divider()

        # equity curve
        period_opts = {"1 Week": "1W", "1 Month": "1M", "3 Months": "3M",
                       "6 Months": "6M", "1 Year": "1A", "All": "all"}
        period_label = st.selectbox(
            "Period", list(period_opts.keys()), index=1, key="portfolio_period"
        )
        period = period_opts[period_label]

        with st.spinner("Loading equity curve…"):
            hist = _get_history(live, period)

        if hist.empty:
            st.info("No portfolio history available yet — make some trades first.")
        else:
            start_eq = hist["equity"].iloc[0]
            end_eq   = hist["equity"].iloc[-1]
            total_pnl     = end_eq - start_eq
            total_pnl_pct = (total_pnl / start_eq * 100) if start_eq else 0
            color = "#26a69a" if total_pnl >= 0 else "#ef5350"

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=hist.index, y=hist["equity"],
                mode="lines", name="Equity",
                line=dict(color=color, width=2),
                fill="tozeroy",
                fillcolor=color.replace(")", ", 0.1)").replace("rgb", "rgba") if "rgb" in color
                          else f"rgba(38,166,154,0.08)" if total_pnl >= 0 else "rgba(239,83,80,0.08)",
            ))
            fig.update_layout(
                height=320,
                margin=dict(l=0, r=0, t=20, b=0),
                xaxis_rangeslider_visible=False,
                yaxis_tickprefix="$",
                yaxis_tickformat=",.0f",
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)

            p1, p2 = st.columns(2)
            p1.metric(
                f"P&L ({period_label})",
                f"${total_pnl:+,.2f}",
                delta=f"{total_pnl_pct:+.2f}%",
                delta_color="normal",
            )
            p2.metric("Start equity", f"${start_eq:,.2f}")

    except Exception as e:
        st.error(f"Could not load account data: {e}")


# ── positions tab ─────────────────────────────────────────────────────────────

with tab_positions:
    try:
        render_positions_table(_get_positions(live))
    except Exception as e:
        st.error(f"Could not load positions: {e}")


# ── orders tab ────────────────────────────────────────────────────────────────

with tab_orders:
    try:
        render_orders_table(_get_orders(live))
    except Exception as e:
        st.error(f"Could not load orders: {e}")


# ── watchlist sync tab ────────────────────────────────────────────────────────

with tab_sync:
    st.subheader("Sync Watchlist to Alpaca")
    st.caption("Pushes your local tickers.yaml (stocks + ETFs) to an Alpaca watchlist named 'Stonks'. Crypto is excluded — Alpaca watchlists only support equities.")

    wl      = load_watchlist()
    local   = [t for t in flat_tickers(wl) if not t.upper().endswith(("-USD", "-USDT"))]

    try:
        alpaca_wl = _get_alpaca_watchlist(live)
    except Exception:
        alpaca_wl = []

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Local watchlist** ({len(local)} tickers)")
        st.write(", ".join(sorted(local)) or "—")
    with c2:
        st.markdown(f"**Alpaca 'Stonks' watchlist** ({len(alpaca_wl)} tickers)")
        st.write(", ".join(sorted(alpaca_wl)) or "— (not created yet)")

    only_local  = sorted(set(local) - set(alpaca_wl))
    only_alpaca = sorted(set(alpaca_wl) - set(local))

    if only_local:
        st.warning(f"Not yet on Alpaca: **{', '.join(only_local)}**")
    if only_alpaca:
        st.info(f"On Alpaca but not in local list: **{', '.join(only_alpaca)}**")
    if not only_local and not only_alpaca and local:
        st.success("Watchlists are in sync.")

    if st.button("Sync now →", type="primary", key="portfolio_sync"):
        try:
            result = sync_watchlist(local, live=live)
            verb = "Created" if result["created"] else "Updated"
            st.success(f"{verb} Alpaca watchlist with {len(result['symbols'])} tickers: {', '.join(result['symbols'])}")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Sync failed: {e}")
