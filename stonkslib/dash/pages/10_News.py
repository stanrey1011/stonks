import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from datetime import datetime, timezone
import streamlit as st

from stonkslib.dash.common import load_watchlist, flat_tickers

st.set_page_config(page_title="News — Stonks", layout="wide")
st.title("News")
st.caption("Latest headlines and sentiment from Finnhub. Requires FINNHUB_API_KEY in .env.")

PROJECT_ROOT = Path(__file__).resolve().parents[3]


# ── ticker selector ───────────────────────────────────────────────────────────

wl = load_watchlist()
all_tickers = flat_tickers(wl)

c1, c2, c3 = st.columns([3, 1, 1])
with c1:
    ticker_input = st.text_input(
        "Ticker",
        placeholder="e.g. AAPL or pick from watchlist →",
        label_visibility="collapsed",
    ).strip().upper()
with c2:
    wl_pick = st.selectbox(
        "Pick from watchlist",
        [""] + sorted(all_tickers),
        label_visibility="collapsed",
    )
with c3:
    days = st.selectbox("Days back", [7, 14, 30], index=1, label_visibility="collapsed")

ticker = ticker_input or wl_pick
if not ticker:
    st.info("Enter a ticker symbol or pick one from the watchlist above.")
    st.stop()


# ── load news (cached) ────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _load_news(ticker: str, days: int) -> dict:
    from stonkslib.utils.news import get_news
    return get_news(ticker, days=days)


col_r, col_ref = st.columns([8, 1])
with col_r:
    st.subheader(f"{ticker} — last {days} days")
with col_ref:
    st.write("")
    if st.button("🔄 Refresh", key="news_refresh"):
        st.cache_data.clear()
        st.rerun()

with st.spinner(f"Loading news for {ticker}…"):
    data = _load_news(ticker, days)

articles  = data.get("articles", [])
sentiment = data.get("sentiment", {})
fetched   = data.get("fetched_at")

if fetched:
    try:
        ft = datetime.fromisoformat(fetched)
        age_min = int((datetime.now(timezone.utc) - ft).total_seconds() / 60)
        st.caption(f"Cached {age_min} min ago · {len(articles)} articles")
    except Exception:
        st.caption(f"{len(articles)} articles")

st.divider()


# ── sentiment strip ───────────────────────────────────────────────────────────

bull = sentiment.get("bullish_pct")
bear = sentiment.get("bearish_pct")
buzz = sentiment.get("buzz")
art_wk = sentiment.get("articles_week")
wk_avg = sentiment.get("weekly_average")
score  = sentiment.get("company_score")

if bull is not None or buzz is not None:
    m1, m2, m3, m4 = st.columns(4)

    if bull is not None:
        bull_pct = f"{bull*100:.0f}%"
        bear_pct = f"{bear*100:.0f}%" if bear is not None else "—"
        m1.metric("Bullish", bull_pct)
        m2.metric("Bearish", bear_pct)
    else:
        m1.metric("Bullish", "—")
        m2.metric("Bearish", "—")

    if buzz is not None:
        buzz_label = f"{buzz:.2f}×"
        buzz_delta = None
        if art_wk is not None and wk_avg and wk_avg > 0:
            buzz_delta = f"{art_wk} articles vs {wk_avg:.0f} avg/wk"
        m3.metric("Buzz ratio", buzz_label, delta=buzz_delta)
    else:
        m3.metric("Buzz ratio", "—")

    if score is not None:
        m4.metric("News score", f"{score:.2f}")
    else:
        m4.metric("News score", "—")

    st.divider()


# ── article feed ─────────────────────────────────────────────────────────────

if not articles:
    st.warning(f"No news articles found for {ticker} in the last {days} days.")
    st.stop()

for art in articles:
    date_s    = art.get("date", "")
    headline  = art.get("headline", "(no headline)")
    source    = art.get("source", "")
    summary   = art.get("summary", "")
    url       = art.get("url", "")

    with st.expander(f"**{headline}**  ·  {source}  ·  {date_s}"):
        if summary and summary != headline:
            st.markdown(summary)
        if url:
            st.markdown(f"[Read full article →]({url})")
