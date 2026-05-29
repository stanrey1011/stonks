import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st

from stonkslib.dash.common import (
    render_account_metrics, render_positions_table, render_orders_table,
)

st.set_page_config(page_title="Robinhood — Stonks", layout="wide")
st.title("Robinhood")

try:
    from stonkslib.broker.robinhood import get_snapshot, connect_url
    from stonkslib.broker.snaptrade import is_configured, is_registered, register_user
    _broker_available = True
except ImportError:
    _broker_available = False

if not _broker_available:
    st.error("SnapTrade client unavailable — check the install.")
    st.stop()

# ── Step 1: keys present? ──────────────────────────────────────────────────────
if not is_configured():
    st.info(
        "Robinhood is read through the **SnapTrade** aggregator (read-only). "
        "Add your SnapTrade partner keys to `.env`, then restart:\n\n"
        "```\nSNAPTRADE_CLIENT_ID=...\nSNAPTRADE_CONSUMER_KEY=...\n```"
    )
    st.stop()

# ── Step 2: user registered? ───────────────────────────────────────────────────
if not is_registered():
    st.warning("SnapTrade user not registered yet — one-time setup.")
    st.caption("Click below to create your SnapTrade user account.")
    if st.button("Register with SnapTrade", key="rh_register"):
        with st.spinner("Registering…"):
            try:
                user = register_user()
                st.success("Registered! **Save these to your `.env`** so they survive a volume wipe:")
                st.code(
                    f"SNAPTRADE_USER_ID={user['userId']}\n"
                    f"SNAPTRADE_USER_SECRET={user['userSecret']}",
                    language="bash",
                )
                st.caption("Once saved to `.env`, restart the container and reload this page.")
            except Exception as e:
                st.error(f"Registration failed: {e}")
    st.stop()

# ── Step 3: account linked? ────────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner="Loading Robinhood positions… (first load only)")
def _load_snapshot() -> dict:
    return get_snapshot()


snap = _load_snapshot()

if not snap["connected"]:
    st.warning("Registered with SnapTrade, but no Robinhood account is linked yet.")
    st.caption(
        "Generate a one-time SnapTrade Connection Portal link, open it, pick "
        "**Robinhood**, log in, and authorize read-only access — then hit Refresh."
    )
    if st.button("Generate connection link", key="rh_connect"):
        try:
            url = connect_url()
            st.success("Open this link (expires in ~5 min), then Refresh:")
            st.markdown(f"[Open SnapTrade Connection Portal →]({url})")
            st.code(url, language=None)
        except Exception as e:
            st.error(f"Could not generate link: {e}")
    st.stop()

_c1, _c2 = st.columns([4, 1])
with _c1:
    st.caption("Cached ~10 min · SnapTrade syncs Robinhood holdings ~once a day · Refresh to refetch")
with _c2:
    if st.button("🔄 Refresh", key="rh_refresh"):
        st.cache_data.clear()
        st.rerun()

st.divider()

tab_overview, tab_positions, tab_orders = st.tabs(["Overview", "Positions", "Orders"])

with tab_overview:
    render_account_metrics(snap["account"])

with tab_positions:
    render_positions_table(snap["positions"])

with tab_orders:
    render_orders_table(snap["orders"])
