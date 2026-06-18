import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd
import streamlit as st

from stonkslib.dash.common import load_watchlist, flat_tickers

st.set_page_config(page_title="Analyst — Stonks", layout="wide")
st.title("🧠 Analyst")
st.caption("One-screen analyst brief — fundamentals, technicals, sentiment, news. "
           "This is the view the analyst agent will consume in the multi-agent setup; "
           "it's assembled by `agents.analyst.analyst_brief()`.")

# ── ticker selector ───────────────────────────────────────────────────────────
wl = load_watchlist()
all_tickers = flat_tickers(wl)

c1, c2, c3 = st.columns([3, 1, 1])
with c1:
    ticker_input = st.text_input(
        "Ticker", placeholder="e.g. AAPL or pick from watchlist →",
        label_visibility="collapsed", key="analyst_ticker",
    ).strip().upper()
with c2:
    wl_pick = st.selectbox("Watchlist", [""] + sorted(all_tickers),
                           label_visibility="collapsed", key="analyst_wl")
with c3:
    interval = st.selectbox("Interval", ["1d", "1wk"], index=0,
                            label_visibility="collapsed", key="analyst_interval")

ticker = ticker_input or wl_pick
if not ticker:
    st.info("Enter a ticker or pick one from the watchlist above.")
    st.stop()


# ── load brief (cached) ───────────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def _brief(ticker: str, interval: str) -> dict:
    from stonkslib.agents.analyst import analyst_brief
    return analyst_brief(ticker, interval=interval)


hdr_l, hdr_r = st.columns([8, 1])
with hdr_r:
    st.write("")
    if st.button("🔄 Refresh", key="analyst_refresh"):
        st.cache_data.clear()
        st.rerun()

with st.spinner(f"Building analyst brief for {ticker}…"):
    brief = _brief(ticker, interval)

fund = brief.get("fundamentals") or {}
earn = brief.get("earnings") or {}
divs = brief.get("dividends") or {}
sent = brief.get("sentiment") or {}
news = brief.get("news") or {}
ta = brief.get("ta") or {}


# ── helpers ───────────────────────────────────────────────────────────────────
def _money(v):
    if v is None:
        return "—"
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(v) >= size:
            return f"${v/size:.2f}{unit}"
    return f"${v:,.0f}"


def _pct(v):
    return "—" if v is None else f"{v*100:.1f}%"


def _num(v, fmt="{:.2f}"):
    return "—" if v is None else fmt.format(v)


# ── summary strip ─────────────────────────────────────────────────────────────
readouts = ta.get("readouts", {})
price = readouts.get("close")
buy_score = ta.get("buy_score", 0.0)
sell_score = ta.get("sell_score", 0.0)
if buy_score > sell_score:
    verdict, vcolor = "BULLISH", "normal"
elif sell_score > buy_score:
    verdict, vcolor = "BEARISH", "inverse"
else:
    verdict, vcolor = "NEUTRAL", "off"

m1, m2, m3, m4 = st.columns(4)
m1.metric(f"{ticker} ({interval})", _num(price, "${:.2f}"))
m2.metric("TA verdict", verdict, delta=f"BUY {buy_score:.1f} / SELL {sell_score:.1f}",
          delta_color=vcolor)
m3.metric("LLM sentiment", f"{sent.get('latest'):.0f}/10" if sent.get("latest") is not None else "—")
m4.metric("Next earnings", earn.get("next_date") or "—")

st.divider()

tab_f, tab_t, tab_s, tab_n = st.tabs(["📊 Fundamentals", "📈 Technicals", "🧠 Sentiment", "📰 News"])

# ── Fundamentals ──────────────────────────────────────────────────────────────
with tab_f:
    if not fund:
        st.info("No fundamentals available (crypto, or yfinance returned nothing).")
    else:
        st.markdown(f"**{fund.get('name') or ticker}** · {fund.get('sector') or '—'}"
                    f" / {fund.get('industry') or '—'}")
        a, b, c, d = st.columns(4)
        a.metric("Market cap", _money(fund.get("market_cap")))
        b.metric("P/E (ttm)", _num(fund.get("trailing_pe")))
        c.metric("P/E (fwd)", _num(fund.get("forward_pe")))
        d.metric("EPS (ttm)", _num(fund.get("eps_ttm")))
        a, b, c, d = st.columns(4)
        a.metric("Beta", _num(fund.get("beta")))
        b.metric("52w range",
                 f"{_num(fund.get('week52_low'),'{:.0f}')}–{_num(fund.get('week52_high'),'{:.0f}')}")
        c.metric("Profit margin", _pct(fund.get("profit_margin")))
        d.metric("Rev growth (yoy)", _pct(fund.get("revenue_growth")))
        a, b, c, _ = st.columns(4)
        a.metric("Analyst target", _num(fund.get("target_mean"), "${:.2f}"))
        b.metric("Recommendation", (fund.get("recommendation") or "—").upper())
        if divs and divs.get("dividend_yield") is not None:
            c.metric("Dividend yield", _pct(divs.get("dividend_yield")))
    if earn.get("next_date"):
        st.caption(f"Next earnings: **{earn['next_date']}**"
                   + (f" · est EPS {earn['next_eps_estimate']}" if earn.get("next_eps_estimate") else ""))

# ── Technicals ────────────────────────────────────────────────────────────────
with tab_t:
    if ta.get("error"):
        st.warning(f"TA unavailable: {ta['error']}")
    else:
        st.caption(f"Latest bar: {ta.get('asof','—')} · votes via the strategy engine "
                   "(same logic as backtests), confluence weights default 1.0.")
        vc1, vc2 = st.columns([1, 1])
        with vc1:
            votes_df = pd.DataFrame(ta.get("votes", []))
            if not votes_df.empty:
                st.dataframe(votes_df, hide_index=True, use_container_width=True)
            st.metric("Confluence", f"BUY {buy_score:.1f}  /  SELL {sell_score:.1f}")
        with vc2:
            ro = ta.get("readouts", {})
            st.markdown("**Latest readings**")
            st.markdown(
                f"- RSI: `{_num(ro.get('rsi'))}`\n"
                f"- MACD: `{_num(ro.get('macd'))}` vs signal `{_num(ro.get('macd_signal'))}`\n"
                f"- Supertrend dir: `{_num(ro.get('st_dir'),'{:.0f}')}`\n"
                f"- Markov bull/bear: `{_num(ro.get('mk_bull'))}` / `{_num(ro.get('mk_bear'))}`\n"
                f"- News sentiment: `{_num(ro.get('news_sent'),'{:.0f}')}/10`"
            )

# ── Sentiment ─────────────────────────────────────────────────────────────────
with tab_s:
    llm = sent.get("llm") or []
    if not llm:
        st.info(f"No LLM sentiment scored for {ticker} yet — seed it on the **News** page.")
    else:
        st.caption("Local-LLM daily score (1–10) + stock-relevant summary.")
        for r in llm:
            score = r.get("score")
            ss = f"{score:.0f}/10" if score is not None else "—"
            with st.expander(f"**{r.get('date','')}** · {ss} · {r.get('n_articles', 0)} articles"):
                if r.get("summary"):
                    st.markdown(r["summary"])
                if r.get("reasoning"):
                    st.caption(f"Why: {r['reasoning']}")
    fh = news.get("finnhub") or {}
    if fh.get("bullish_pct") is not None:
        st.divider()
        st.caption(f"Finnhub: bullish {fh.get('bullish_pct')} · bearish {fh.get('bearish_pct')} "
                   f"· news score {fh.get('company_score')}")

# ── News ──────────────────────────────────────────────────────────────────────
with tab_n:
    articles = news.get("articles") or []
    if not articles:
        st.info(f"No recent articles for {ticker}.")
    else:
        for art in articles:
            with st.expander(f"**{art.get('headline','(no headline)')}** · "
                             f"{art.get('source','')} · {art.get('date','')}"):
                if art.get("summary") and art["summary"] != art.get("headline"):
                    st.markdown(art["summary"])
                if art.get("url"):
                    st.markdown(f"[Read full article →]({art['url']})")
