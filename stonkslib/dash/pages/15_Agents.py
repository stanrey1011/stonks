import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd
import streamlit as st

from stonkslib.dash.common import load_watchlist, flat_tickers

st.set_page_config(page_title="Agents — Stonks", layout="wide")
st.title("🏦 Agents — Hedge-Fund Desk")
st.caption("One local model (Hermes) wearing every hat: analysts → bull/bear debate "
           "→ portfolio manager. Facts on the left are computed by stonks; the chain "
           "on the right reasons over them. The manager's call is bucketed by vehicle "
           "(LEAP / DCA / Swing) at the bottom.")

# ── ticker selector ─────────────────────────────────────────────────────────────
wl = load_watchlist()
all_tickers = flat_tickers(wl)

c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
with c1:
    ticker_input = st.text_input(
        "Ticker", placeholder="e.g. NVDA",
        label_visibility="collapsed", key="agents_ticker",
    ).strip().upper()
with c2:
    wl_pick = st.selectbox("Watchlist", [""] + sorted(all_tickers),
                           label_visibility="collapsed", key="agents_wl")
with c3:
    interval = st.selectbox("Interval", ["1d", "1wk"], index=0,
                            label_visibility="collapsed", key="agents_interval")
with c4:
    run = st.button("▶ Run desk", type="primary", key="agents_run", use_container_width=True)

ticker = ticker_input or wl_pick
if not ticker:
    st.info("Enter a ticker or pick one from the watchlist, then **Run desk**.")
    st.stop()


# ── run the chain (cached — LLM calls are expensive) ────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def _run(ticker: str, interval: str) -> dict:
    from stonkslib.agents.orchestrator import run_fund
    return run_fund(ticker, interval=interval)


hdr_l, hdr_r = st.columns([8, 1])
with hdr_r:
    if st.button("🔄 Refresh", key="agents_refresh"):
        st.cache_data.clear()
        st.rerun()

# Only run when asked (or when a prior result is cached for this ticker/interval).
state_key = f"agents_done::{ticker}::{interval}"
if run:
    st.session_state[state_key] = True
if not st.session_state.get(state_key):
    st.info(f"Press **Run desk** to send {ticker} through the agent chain.")
    st.stop()

with st.spinner(f"Running the desk on {ticker}… (analysts → researchers → PM)"):
    report = _run(ticker, interval)

snap = report.get("snapshot") or {}
agents = report.get("agents") or []
verdict = report.get("verdict") or {}


# ── helpers ─────────────────────────────────────────────────────────────────────
def _money(v):
    if v is None:
        return "—"
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(v) >= size:
            return f"${v/size:.2f}{unit}"
    return f"${v:,.0f}"


def _num(v, fmt="{:.2f}"):
    return "—" if v is None else fmt.format(v)


_VOTE_COLOR = {"BUY": "green", "SELL": "red", "—": "gray"}
_LEAN_COLOR = {
    "buy_call": "green", "buy": "green", "accumulate": "green",
    "buy_put": "orange", "sell": "red", "skip": "gray", "avoid": "red",
    "wait": "orange", "hold": "blue",
}


def _lean_badge(lean: str) -> str:
    color = _LEAN_COLOR.get(lean, "gray")
    return f":{color}[**{lean.upper().replace('_', ' ')}**]"


# ── per-vehicle verdict banner (top of the reasoning payoff) ────────────────────
verdicts = verdict.get("verdicts") or {}
conv = verdict.get("conviction", "—")
st.markdown(f"### Verdict — {ticker} · conviction **{conv}**")
vc1, vc2, vc3 = st.columns(3)
for col, key, label in ((vc1, "leap", "📈 LEAP"), (vc2, "dca", "💵 DCA"), (vc3, "swing", "🔁 Swing")):
    v = verdicts.get(key) or {}
    with col:
        st.markdown(f"**{label}** — {_lean_badge(str(v.get('lean', '—')))}")
        st.caption(v.get("rationale") or "—")
        hint = v.get("suggested") or v.get("suggested_entry")
        if hint and str(hint).lower() not in ("null", "none"):
            st.caption(f"↳ {hint}")
if verdict.get("summary"):
    st.info(verdict["summary"])

st.divider()

# ── FACTS (left)  |  REASONING CHAIN (right) ────────────────────────────────────
left, right = st.columns([1, 1])

with left:
    st.subheader("📊 Facts")
    price = snap.get("price") or {}
    conf = snap.get("confluence") or {}
    edge = snap.get("edge") or {}
    leap = snap.get("leap_edge") or {}
    fund = snap.get("fundamentals") or {}
    earn = snap.get("earnings") or {}
    sent = snap.get("sentiment") or {}

    if "error" not in price:
        m1, m2, m3 = st.columns(3)
        m1.metric("Price", _num(price.get("close"), "${:.2f}"),
                  delta=f"{price.get('day_change_pct')}%" if price.get("day_change_pct") is not None else None)
        m2.metric("BUY conf", _num(conf.get("buy_score"), "{:.2f}"))
        m3.metric("SELL conf", _num(conf.get("sell_score"), "{:.2f}"))

    st.markdown("**Confluence votes**")
    votes = conf.get("votes") or []
    if votes:
        st.markdown("  ".join(f":{_VOTE_COLOR.get(v['vote'],'gray')}[{v['indicator']} {v['vote']}]"
                              for v in votes))
    else:
        st.caption(conf.get("error") or "no votes")

    st.markdown("**Validated edge**")
    def _edge_line(e, kind):
        best = e.get("best")
        if not e or "error" in e:
            return f"- {kind}: ⚠️ {e.get('error','n/a')}"
        if not best:
            return f"- {kind}: ✗ none validated"
        if kind == "LEAP":
            return (f"- {kind}: ✓ {best['strategy']} ({best.get('option_type','')}) · "
                    f"{best.get('win_rate',0):.0%} win · {best.get('avg_pnl_pct',0):+.1f}%/trade · "
                    f"{best.get('trades')} trades")
        return (f"- {kind}: ✓ {best['strategy']} · {best.get('win_rate',0):.0%} win · "
                f"${best.get('net_pnl',0):,.0f} · {best.get('trades')} trades")
    st.markdown(_edge_line(edge, "Swing") + "\n" + _edge_line(leap, "LEAP"))

    st.markdown("**Fundamentals**")
    st.markdown(
        f"- {fund.get('name') or ticker} · {fund.get('sector') or '—'}\n"
        f"- Mkt cap {_money(fund.get('market_cap'))} · P/E fwd {_num(fund.get('forward_pe'))} "
        f"/ ttm {_num(fund.get('trailing_pe'))}\n"
        f"- Target {_num(fund.get('target_mean'), '${:.2f}')} · rec "
        f"{(fund.get('recommendation') or '—').upper()}"
    )

    st.markdown("**Earnings & sentiment**")
    st.markdown(
        f"- Next earnings: {earn.get('next_date') or '—'}\n"
        f"- LLM sentiment: {_num(sent.get('latest'), '{:.0f}')}/10"
    )

    # freshness footer
    fr = snap.get("freshness") or {}
    stale = [k for k, v in fr.items() if v.get("stale")]
    if stale:
        st.caption(f"⚠️ stale: {', '.join(stale)}")

with right:
    st.subheader("🧠 Reasoning chain")
    _STAGE_ICON = {"analyst": "🔎", "research": "⚖️", "manager": "🏛️"}
    for a in agents:
        out = a.get("output") or {}
        icon = _STAGE_ICON.get(a.get("stage"), "•")
        with st.expander(f"{icon} {a['title']}", expanded=(a["stage"] != "manager")):
            if "error" in out:
                st.warning(f"unavailable: {out['error']}")
                continue
            # render known fields in a stable order, fall back to raw JSON
            for field in ("lean", "confidence", "thesis", "trend_read", "signal_summary",
                          "edge_note", "valuation_read", "argument", "summary"):
                if out.get(field):
                    label = field.replace("_", " ").title()
                    st.markdown(f"**{label}:** {out[field]}")
            for listf in ("quality_flags", "key_supports", "key_concerns"):
                if out.get(listf):
                    st.markdown("\n".join(f"- {x}" for x in out[listf]))
            for tail in ("biggest_risk_acknowledged", "what_would_change_my_mind"):
                if out.get(tail):
                    st.caption(f"{tail.replace('_',' ')}: {out[tail]}")
