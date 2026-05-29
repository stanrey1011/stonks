import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import os
import streamlit as st
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

from stonkslib.dash.common import load_watchlist, flat_tickers

st.set_page_config(page_title="Stonks — Home", layout="wide")

# ── header ────────────────────────────────────────────────────────────────────

st.title("Welcome to Stonks")
st.caption("Your personal stock and crypto analysis dashboard.")

wl   = load_watchlist()
tickers = flat_tickers(wl)
now  = datetime.now(timezone.utc).strftime("%A, %B %d, %Y · %H:%M UTC")
st.markdown(f"**{now}**  ·  {len(tickers)} ticker{'s' if len(tickers) != 1 else ''} on your watchlist")

st.divider()

# ── system status ─────────────────────────────────────────────────────────────

st.subheader("System Status")


@st.cache_data(ttl=300, show_spinner=False)
def _check_finnhub() -> tuple[bool, str]:
    key = os.getenv("FINNHUB_API_KEY", "")
    if not key:
        return False, "FINNHUB_API_KEY not set in .env"
    try:
        import requests
        r = requests.get(
            "https://finnhub.io/api/v1/stock/profile2",
            params={"symbol": "AAPL", "token": key},
            timeout=5,
        )
        if r.status_code == 200 and r.json().get("name"):
            return True, "Connected"
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)[:60]


@st.cache_data(ttl=300, show_spinner=False)
def _check_ollama() -> tuple[bool, str]:
    try:
        import requests
        base = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        r = requests.get(f"{base}/api/tags", timeout=3)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            label = f"{len(models)} model{'s' if len(models) != 1 else ''} loaded"
            return True, label
        return False, f"HTTP {r.status_code}"
    except Exception:
        return False, "Not running or unreachable"


@st.cache_data(ttl=300, show_spinner=False)
def _check_yfinance() -> tuple[bool, str]:
    try:
        import yfinance as yf
        import warnings
        warnings.filterwarnings("ignore")
        t = yf.Ticker("AAPL")
        hist = t.history(period="1d", auto_adjust=True)
        if not hist.empty:
            return True, "Connected"
        return False, "Empty response"
    except Exception as e:
        return False, str(e)[:60]


def _alpaca_check(key: str, secret: str, base: str) -> tuple[bool, str]:
    if not key or not secret:
        return False, "Keys not set in .env"
    try:
        import requests
        r = requests.get(
            f"{base}/v2/account",
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
            timeout=5,
        )
        if r.status_code == 200:
            acct = r.json()
            equity = float(acct.get("equity", 0))
            status = acct.get("status", "")
            return True, f"${equity:,.0f} equity · {status}"
        if r.status_code == 403:
            return False, "Invalid credentials"
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)[:60]


@st.cache_data(ttl=300, show_spinner=False)
def _check_alpaca_paper() -> tuple[bool, str]:
    return _alpaca_check(
        os.getenv("ALPACA_API_KEY", ""),
        os.getenv("ALPACA_SECRET_KEY", ""),
        "https://paper-api.alpaca.markets",
    )


@st.cache_data(ttl=300, show_spinner=False)
def _check_alpaca_live() -> tuple[bool, str]:
    key    = os.getenv("ALPACA_LIVE_API_KEY", "")
    secret = os.getenv("ALPACA_LIVE_SECRET_KEY", "")
    if not key or not secret:
        return False, "Pending — add ALPACA_LIVE_API_KEY to .env"
    return _alpaca_check(key, secret, "https://api.alpaca.markets")


@st.cache_data(ttl=300, show_spinner=False)
def _check_robinhood() -> tuple[bool, str]:
    # Light check only — verifying the linked account (one API call). Fetching equity
    # would pull all positions (slow), which isn't worth it for a status badge.
    from stonkslib.broker import robinhood as rh
    if not rh.is_configured():
        return False, "SnapTrade keys not set in .env"
    try:
        return (True, "Connected") if rh.is_connected() else (False, "Not linked — connect via SnapTrade")
    except Exception as e:
        return False, str(e)[:60]


def _status_badge(ok: bool, msg: str, label: str):
    if ok:
        dot   = "<span style='color:#66bb6a; font-size:1.1em'>●</span>"
        color = "#66bb6a"
        state = "Connected"
    else:
        dot   = "<span style='color:#ef5350; font-size:1.1em'>●</span>"
        color = "#ef5350"
        state = "Error"
    st.markdown(
        f"{dot} &nbsp;**{label}**<br>"
        f"<span style='font-size:0.8em; color:{color}'>{state}</span><br>"
        f"<span style='font-size:0.75em; opacity:0.6'>{msg}</span>",
        unsafe_allow_html=True,
    )


col_fh, col_yf, col_ol, col_ap, col_al, col_rh = st.columns(6)

with col_fh:
    ok, msg = _check_finnhub()
    _status_badge(ok, msg, "Finnhub")

with col_yf:
    ok, msg = _check_yfinance()
    _status_badge(ok, msg, "yfinance")

with col_ol:
    ok, msg = _check_ollama()
    _status_badge(ok, msg, "Ollama")

with col_ap:
    ok, msg = _check_alpaca_paper()
    _status_badge(ok, msg, "Alpaca Paper")

with col_al:
    ok, msg = _check_alpaca_live()
    _status_badge(ok, msg, "Alpaca Live")

with col_rh:
    ok, msg = _check_robinhood()
    _status_badge(ok, msg, "Robinhood")

st.caption("Status refreshes every 5 minutes. Click 🔄 below to force a recheck.")
if st.button("🔄 Recheck", key="home_recheck"):
    st.cache_data.clear()
    st.rerun()

st.divider()

# ── what is this? ─────────────────────────────────────────────────────────────

st.subheader("What does this tool do?")
st.markdown("""
This dashboard watches a list of stocks, ETFs, and crypto coins for you.
It automatically downloads price data every day and runs a set of **technical indicators** —
math formulas that look at price history and try to spot patterns that often happen before a stock moves up or down.

When enough indicators agree, it fires an **alert**. It does not buy or sell anything automatically —
it just tells you *"hey, something might be happening with this ticker."*
You decide what to do with that information.
""")

st.divider()

# ── quick start ───────────────────────────────────────────────────────────────

st.subheader("Where do I start?")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### 1. Check Alerts")
    st.markdown("""
Go to **Alerts** (left sidebar, under Analysis).

Click **Scan all tickers**. You'll see green cards for BUY signals
and red cards for SELL signals across your whole watchlist.

This is the first thing to check each morning.
""")

with col2:
    st.markdown("### 2. Dig into a ticker")
    st.markdown("""
See something interesting in Alerts? Go to **Chart** and pick that ticker.

Turn on overlays (RSI, Bollinger Bands, Moving Averages) to see
why the signal fired — the chart draws them right on top of the price.

Then go to **Confluence** to see how many indicators agreed on the same day.
More agreement = higher conviction.
""")

with col3:
    st.markdown("### 3. Check the backtest")
    st.markdown("""
Want to know if a strategy actually worked in the past?

Go to **Backtest**, pick a ticker, and hit **Run Backtest**.
It tests every strategy against real historical prices and ranks them —
1st place gets the gold medal.

Higher confidence score = better balance of returns, win rate, and safety.
""")

st.divider()

# ── glossary ──────────────────────────────────────────────────────────────────

st.subheader("What do these words mean?")

with st.expander("Indicators, signals, and strategies"):
    st.markdown("""
**Indicator** — a formula that calculates something about price history.
Examples: RSI (is this stock overbought or oversold?), Bollinger Bands (is price unusually far from average?),
Moving Averages (is the short-term trend above or below the long-term trend?).

**Signal** — when an indicator crosses a threshold and says "something is happening."
A BUY signal means conditions look bullish (price might go up).
A SELL signal means conditions look bearish (price might go down).

**Strategy** — a ruleset that combines one or more indicators. For example,
the RSI strategy buys when RSI drops below 30 (oversold) and sells when RSI rises above 70 (overbought).

**Confluence** — when multiple indicators agree on the same day. Two indicators saying BUY is stronger than just one.
""")

with st.expander("BUY and SELL — what do they really mean?"):
    st.markdown("""
These are not instructions to buy or sell. They are signal *types*:

- **BUY signal** — conditions suggest the price might go UP. Could be a good time to *consider* entering a position.
- **SELL signal** — conditions suggest the price might go DOWN. Could be a good time to *consider* exiting.

Markets are unpredictable. These signals are right more often than random chance,
but they are never guaranteed. Always do your own research.
""")

with st.expander("What is a LEAP?"):
    st.markdown("""
A LEAP is a long-term options contract — it gives you the *right* (but not the obligation) to buy or sell
a stock at a fixed price, up to 1-2 years in the future.

LEAPs cost a fraction of buying the stock outright, but if the stock moves your way you can make
a much larger percentage return. The risk: if the stock doesn't move enough in time, you lose the premium you paid.

Use the **Pipeline** page → Alerts tab or the **LEAP scanner** commands in the terminal for LEAP-specific signals.
""")

with st.expander("What is a trailing stop?"):
    st.markdown("""
A trailing stop is an automatic exit rule. Instead of exiting when an indicator says SELL,
you exit when the price drops a certain percentage below its highest point since you bought in.

Example with 12% trailing stop: you buy at $100. Price rises to $150 — your stop moves up to $132.
If price then drops to $132, you exit. You captured most of the gain, even if no indicator fired.

You can compare trailing stop exits vs indicator exits on the **Backtest** page.
""")

st.divider()

# ── page guide ────────────────────────────────────────────────────────────────

st.subheader("Page guide")

pages = [
    ("🚨", "Alerts",     "Analysis", "Full watchlist scan — see all BUY/SELL signals across every ticker in one place. Start here."),
    ("📊", "Confluence", "Analysis", "For a specific ticker: how many indicators agreed on each date? More agreement = stronger signal."),
    ("📈", "Chart",      "Analysis", "Interactive price chart. Overlay indicators and see exactly what triggered a signal visually."),
    ("🔔", "Signals",    "Analysis", "Quick single-ticker signal check. Good for spot-checking one stock on demand."),
    ("🦙", "Alpaca",     "Portfolio", "Live view of your Alpaca brokerage account — equity, positions, recent orders, and watchlist sync."),
    ("🪶", "Robinhood",  "Portfolio", "Live view of your Robinhood account — equity, positions, and recent orders (read-only)."),
    ("🧪", "Backtest",   "Trading",  "Test strategies against real historical data. Ranks them by a composite confidence score."),
    ("📋", "Trades",     "Trading",  "Drill into individual entry/exit trades from a saved backtest."),
    ("⭐", "Watchlist",  "Configuration", "Add or remove tickers. Automatically fetches data for new ones."),
    ("⚙️", "Pipeline",  "Configuration", "Re-fetch data, run alert scans with full options, or run the strategy optimizer."),
    ("💬", "Chat",      "AI", "Ask the Stonks Assistant anything — signals, setups, LEAP ideas. Powered by Ollama."),
]

for icon, title, section, desc in pages:
    st.markdown(f"**{icon} {title}** `{section}` — {desc}")
