import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st

from stonkslib.dash.common import (
    render_account_metrics, render_positions_table,
    render_options_table, render_orders_table,
    load_watchlist, save_watchlist, flat_tickers,
)


def _value(df) -> float:
    """Total market value of a positions/options frame (0 if empty)."""
    if df is None or df.empty or "market_value" not in df:
        return 0.0
    return float(df["market_value"].sum())


def _ago(iso: str) -> str:
    """Human 'time ago' for a SnapTrade ISO sync timestamp."""
    if not iso:
        return "never"
    from datetime import datetime, timezone
    try:
        ts = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        secs = (datetime.now(timezone.utc) - ts).total_seconds()
    except Exception:
        return str(iso)[:16]
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def _extract_return_pct(raw) -> float | None:
    """Best-effort pull of a return percentage out of SnapTrade's returnRates blob,
    whose shape varies by brokerage. Returns None if nothing parseable."""
    if isinstance(raw, dict):
        if "_error" in raw:
            return None
        raw = raw.get("return_rates") or raw.get("returnRates") or raw.get("data") or raw
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                for k in ("return_percent", "returnPercent", "rate", "annualized"):
                    if item.get(k) is not None:
                        try:
                            return float(item[k])
                        except (TypeError, ValueError):
                            pass
    return None

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

stocks, crypto, options, orders = (
    snap["stocks"], snap["crypto"], snap["options"], snap["orders"],
)
counts = snap.get("debug", {}).get("counts", {})

tab_overview, tab_stocks, tab_crypto, tab_options, tab_orders = st.tabs([
    "Overview",
    f"Stocks ({counts.get('stocks', 0)})",
    f"Crypto ({counts.get('crypto', 0)})",
    f"Options ({counts.get('options', 0)})",
    f"Orders ({counts.get('orders', 0)})",
])

with tab_overview:
    acct = snap["account"]
    render_account_metrics(acct)

    st.divider()
    st.caption("Holdings by asset class")
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Stocks & ETFs", f"${_value(stocks):,.2f}")
    b2.metric("Crypto",        f"${_value(crypto):,.2f}")
    b3.metric("Options",       f"${_value(options):,.2f}")
    pnl = acct.get("total_unrealized_pnl", 0.0)
    b4.metric(
        "Unrealized P&L", f"${pnl:+,.2f}",
        delta=f"{acct.get('total_pnl_pct', 0.0):+.2f}%", delta_color="normal",
    )
    st.caption(f"Cost basis ${acct.get('total_cost_basis', 0.0):,.2f} · open P&L across all holdings")

    # ── per-account sync freshness ───────────────────────────────────────────
    accts = snap.get("accounts", [])
    if accts:
        st.divider()
        st.caption("Linked accounts · SnapTrade syncs Robinhood holdings ~once a day")
        cols = st.columns(len(accts))
        for col, a in zip(cols, accts):
            with col:
                st.metric(a["name"], f"${a['total_value']:,.2f}")
                st.caption(f"{a['number']} · synced {_ago(a['last_sync'])}")

    # ── performance & activity probe (beta) ──────────────────────────────────
    dbg = snap.get("debug", {})
    rets = [_extract_return_pct(v) for v in dbg.get("raw_return_rates", {}).values()]
    rets = [r for r in rets if r is not None]
    n_act = dbg.get("counts", {}).get("activities", 0)
    with st.expander(f"📈 Performance & activity (beta) · {n_act} activities", expanded=False):
        if rets:
            st.metric("Reported return", f"{sum(rets) / len(rets):+.2f}%")
        else:
            st.caption("SnapTrade returned no parseable return rate for Robinhood (often unsupported).")
        st.caption("Raw `returnRates` per account:")
        st.json(dbg.get("raw_return_rates", {}))
        st.caption(
            "Raw `activities` (dividends/deposits/trades). Robinhood usually syncs "
            "holdings only, so an empty list here is expected:"
        )
        st.json(dbg.get("raw_activities", {}))

with tab_stocks:
    # Import Robinhood stock/ETF holdings into the watchlist (crypto + options excluded —
    # the snapshot already splits those out). Only adds symbols not already tracked.
    _held = sorted({str(s).upper().strip() for s in stocks["symbol"]
                    if str(s).strip()}) if (stocks is not None and not stocks.empty
                                            and "symbol" in stocks.columns) else []
    _missing = [s for s in _held if s not in set(flat_tickers())]
    ci1, ci2 = st.columns([3, 1])
    ci1.caption(
        f"{len(_held)} stock holding(s) · "
        + (f"**{len(_missing)}** not yet in your watchlist: {', '.join(_missing)}"
           if _missing else "all already in your watchlist ✓")
    )
    if ci2.button(f"➕ Import {len(_missing)} to watchlist", key="rh_import_stocks",
                  disabled=not _missing, use_container_width=True):
        # Add the symbols only — fetching price data for a large batch inline is slow and
        # unreliable. Use the Watchlist page's "Pull latest data" button (or wait for the
        # nightly scheduler) to fetch their data.
        wl = load_watchlist()
        wl.setdefault("stocks", [])
        wl["stocks"].extend(s for s in _missing if s not in wl["stocks"])
        save_watchlist(wl)
        st.cache_data.clear()
        st.success(
            f"Added {len(_missing)} ticker(s) to your watchlist: {', '.join(_missing)}.  "
            "Go to **Watchlist → 🔄 Pull latest data** to fetch their price data "
            "(or the nightly refresh will do it automatically)."
        )

    render_positions_table(stocks)

with tab_crypto:
    render_positions_table(crypto)

with tab_options:
    if options is None or options.empty:
        st.warning(
            "No option positions came back. SnapTrade syncs Robinhood **holdings** "
            "(not always options), so this can be empty even if you hold contracts. "
            "Expand the raw payload below to see exactly what the options endpoint "
            "returned per account."
        )
    render_options_table(options)
    with st.expander("🔍 Raw options payload (debug — verify population)"):
        st.caption(
            "One entry per linked Robinhood account. An empty list `[]` means "
            "SnapTrade's Robinhood integration returned no options for that account."
        )
        st.json(snap.get("debug", {}).get("raw_options", {}))
        st.caption("Linked accounts:")
        st.json(snap.get("debug", {}).get("accounts", []))

with tab_orders:
    render_orders_table(orders)
