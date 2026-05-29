import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st
import yaml
from datetime import datetime, timezone

from stonkslib.dash.common import (
    load_watchlist, flat_tickers, STRATEGY_DIR,
    save_alert_cache, load_alert_cache,
)

st.set_page_config(page_title="Alerts — Stonks", layout="wide")
st.title("Alerts")
st.caption("Full watchlist scan on the latest bar. Aggregates signals across all strategies and displays BUY/SELL cards per ticker. Results stay on screen until you re-scan — adjust filters without re-running.")

wl = load_watchlist()
tickers = flat_tickers(wl)
if not tickers:
    st.warning("No tickers in watchlist. Add some on the Watchlist page.")
    st.stop()

strategy_files = sorted(STRATEGY_DIR.glob("*.yaml"))

# ── strategy names for filter (from YAML files) ───────────────────────────────

_all_strategy_names = []
for _p in strategy_files:
    try:
        import yaml as _yaml
        _s = _yaml.safe_load(open(_p))
        _all_strategy_names.append(_s.get("name", _p.stem))
    except Exception:
        _all_strategy_names.append(_p.stem)

# ── sidebar controls ──────────────────────────────────────────────────────────

with st.sidebar:
    interval        = st.selectbox("Interval", ["1d", "1wk", "1h"])
    min_signals     = st.slider("Min signals (confluence)", 1, 8, 1)
    confirm_weekly  = st.checkbox("Confirm with weekly trend", value=False,
                                  help="Only pass 1d signals that align with weekly 20/50 EMA direction")
    show_no_signal  = st.checkbox("Show tickers with no signal", value=False)

    st.markdown("**Filter results**")
    dir_filter      = st.radio("Direction", ["All", "BUY only", "SELL only"], horizontal=True)
    included_strats = st.multiselect(
        "Strategies", _all_strategy_names, default=_all_strategy_names,
        help="Uncheck a strategy to hide its signals from results",
    )

# ── scan button ───────────────────────────────────────────────────────────────

col_btn, col_ts = st.columns([2, 5])
run = col_btn.button("Scan all tickers", type="primary", use_container_width=True)
ts_placeholder = col_ts.empty()

# ── restore from disk if session state is empty ───────────────────────────────
if "alert_results" not in st.session_state:
    cached = load_alert_cache()
    if cached:
        st.session_state["alert_results"]  = cached["results"]
        st.session_state["alert_ts"]       = cached["ts"]
        st.session_state["alert_interval"] = cached["interval"]
        st.session_state["alert_min"]      = cached["min_signals"]

if "alert_ts" in st.session_state:
    ts_placeholder.caption(f"Last scanned: **{st.session_state['alert_ts']}**  •  "
                           f"{st.session_state.get('alert_interval','?')} interval  •  "
                           f"min signals: {st.session_state.get('alert_min','?')}")

# ── run scan ──────────────────────────────────────────────────────────────────

if run:
    from stonkslib.alerts.signals import check_signals

    aggregated: dict[str, dict] = {}
    progress = st.progress(0, text="Starting scan…")
    total = len(tickers)

    for i, ticker in enumerate(tickers):
        progress.progress(i / total, text=f"Scanning {ticker}…")
        ticker_signals = []

        for path in strategy_files:
            opt_dir = STRATEGY_DIR / "optimized"
            # per-ticker → global → base fallback
            for candidate in [
                opt_dir / f"{path.stem}_{ticker}_optimized.yaml",
                opt_dir / f"{path.stem}_optimized.yaml",
                path,
            ]:
                if candidate.exists():
                    active = candidate
                    break

            with open(active) as f:
                strat = yaml.safe_load(f)

            sigs = check_signals(
                ticker, interval, strat,
                min_signals=min_signals,
                confirm_weekly=confirm_weekly,
            )
            if sigs:
                strat_name = strat.get("name", path.stem)
                for s in sigs:
                    ticker_signals.append({**s, "strategy": strat_name})

        aggregated[ticker] = {
            "close": ticker_signals[0]["close"] if ticker_signals else None,
            "date":  ticker_signals[0]["date"][:10] if ticker_signals else None,
            "signals": ticker_signals,
        }

    progress.empty()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    st.session_state["alert_results"]  = aggregated
    st.session_state["alert_ts"]       = ts
    st.session_state["alert_interval"] = interval
    st.session_state["alert_min"]      = min_signals
    save_alert_cache(aggregated, ts, interval, min_signals)
    ts_placeholder.caption(f"Last scanned: **{ts}**  •  "
                           f"{interval} interval  •  min signals: {min_signals}")

# ── render results ────────────────────────────────────────────────────────────

if "alert_results" not in st.session_state:
    st.info("Click **Scan all tickers** to run the first scan.")
    st.stop()

results: dict = st.session_state["alert_results"]

# separate into buy, sell, none — apply strategy filter first
buy_tickers  = {}
sell_tickers = {}
both_tickers = {}
none_tickers = []

for ticker, data in results.items():
    sigs = [s for s in data["signals"] if s.get("strategy") in included_strats]
    has_buy  = any(s["type"] == "BUY"  for s in sigs)
    has_sell = any(s["type"] == "SELL" for s in sigs)
    filtered_data = {**data, "signals": sigs}
    if has_buy and has_sell:
        both_tickers[ticker] = filtered_data
    elif has_buy:
        buy_tickers[ticker] = filtered_data
    elif has_sell:
        sell_tickers[ticker] = filtered_data
    else:
        none_tickers.append(ticker)

# apply direction filter
if dir_filter == "BUY only":
    sell_tickers = {}
    both_tickers = {t: d for t, d in both_tickers.items()
                    if any(s["type"] == "BUY" for s in d["signals"])}
elif dir_filter == "SELL only":
    buy_tickers = {}
    both_tickers = {t: d for t, d in both_tickers.items()
                    if any(s["type"] == "SELL" for s in d["signals"])}

total_buy  = sum(1 for t in list(buy_tickers) + list(both_tickers))
total_sell = sum(1 for t in list(sell_tickers) + list(both_tickers))

m1, m2, m3, m4 = st.columns(4)
m1.metric("Tickers scanned", len(results))
m2.metric("BUY signals",  total_buy,  delta=None)
m3.metric("SELL signals", total_sell, delta=None)
m4.metric("No signal",    len(none_tickers))

st.divider()


def _signal_card(ticker: str, data: dict, show_types=("BUY", "SELL")):
    """Render a single ticker card."""
    sigs = [s for s in data["signals"] if s["type"] in show_types]
    if not sigs:
        return

    types_present = {s["type"] for s in sigs}
    if types_present == {"BUY"}:
        border = "#26a69a"
        badge  = "🟢 BUY"
    elif types_present == {"SELL"}:
        border = "#ef5350"
        badge  = "🔴 SELL"
    else:
        border = "#ffa726"
        badge  = "🟠 MIXED"

    price_str = f"${data['close']:,.2f}" if data["close"] else "—"
    date_str  = data["date"] or "—"

    st.markdown(
        f"""
        <div style="border-left: 4px solid {border}; padding: 8px 12px;
                    background: rgba(255,255,255,0.04); border-radius: 4px; margin-bottom: 4px;">
          <strong style="font-size:1.05em">{ticker}</strong>
          &nbsp;&nbsp;<span style="color:{border}">{badge}</span>
          &nbsp;&nbsp;<span style="opacity:0.6; font-size:0.85em">{price_str} · {date_str}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # group by strategy
    by_strat: dict[str, list[str]] = {}
    for s in sigs:
        by_strat.setdefault(s["strategy"], []).append(
            f"{'▲' if s['type']=='BUY' else '▼'} {s['reason']}"
        )

    for strat_name, reasons in by_strat.items():
        st.caption(f"**{strat_name}:** " + "  |  ".join(reasons))


def _render_section(label: str, ticker_dict: dict, show_types=("BUY", "SELL"), cols=3):
    if not ticker_dict:
        return
    st.subheader(label)
    items = list(ticker_dict.items())
    for row_start in range(0, len(items), cols):
        row_items = items[row_start:row_start + cols]
        columns = st.columns(cols)
        for col, (ticker, data) in zip(columns, row_items):
            with col:
                _signal_card(ticker, data, show_types=show_types)
    st.write("")


if dir_filter in ("All", "BUY only"):
    _render_section(f"🟢 BUY  ({len(buy_tickers)} ticker{'s' if len(buy_tickers)!=1 else ''})",
                    buy_tickers, show_types=("BUY",))

if dir_filter in ("All", "SELL only"):
    _render_section(f"🔴 SELL  ({len(sell_tickers)} ticker{'s' if len(sell_tickers)!=1 else ''})",
                    sell_tickers, show_types=("SELL",))

if both_tickers:
    _render_section(f"🟠 Mixed signals  ({len(both_tickers)})",
                    both_tickers)

if show_no_signal and none_tickers:
    st.subheader(f"No signal  ({len(none_tickers)})")
    st.caption("  ·  ".join(none_tickers))
