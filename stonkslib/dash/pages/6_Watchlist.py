import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import json
from datetime import datetime, date, timezone
import streamlit as st
import pandas as pd
import subprocess

from stonkslib.dash.common import (
    load_watchlist, save_watchlist, STONKS_BIN, VALID_CATEGORIES, CLEAN_DIR,
    load_alert_cache,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
_EARNINGS_DIR = PROJECT_ROOT / "data" / "ticker_data" / "earnings"

st.set_page_config(page_title="Watchlist — Stonks", layout="wide")
st.title("Watchlist")
st.caption("Tickers tracked across all pages. Shows last close price, day change, and data freshness. Add a symbol below to fetch data automatically.")


# ── per-ticker data (cached) ──────────────────────────────────────────────────

def _calc_rsi(close: "pd.Series", period: int = 14) -> float | None:
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    last_loss = loss.iloc[-1]
    if last_loss == 0:
        return 100.0
    rs = gain.iloc[-1] / last_loss
    return round(100 - (100 / (1 + rs)), 1)


@st.cache_data(ttl=3600, show_spinner=False)
def _ticker_row(ticker: str) -> dict:
    path = CLEAN_DIR / ticker / "1d.parquet"
    if not path.exists():
        return {"price": None, "change": None, "freshness": "Missing", "age_h": None}

    df = pd.read_parquet(path)
    df.columns = df.columns.str.title()
    df = df.sort_index()

    now   = datetime.now(timezone.utc)
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    age_h = (now - mtime).total_seconds() / 3600
    freshness = "Fresh" if age_h < 24 else ("Stale" if age_h < 72 else "Old")

    if df.empty:
        return {"price": None, "change": None, "freshness": freshness, "age_h": age_h}

    close = df["Close"]
    price = float(close.iloc[-1])

    change = (
        (price - float(close.iloc[-2])) / float(close.iloc[-2]) * 100
        if len(df) >= 2 else None
    )

    # 52-week window (≈252 trading days)
    w52 = close.tail(252)
    high_52w = float(w52.max())
    low_52w  = float(w52.min())
    pct_from_high = (price - high_52w) / high_52w * 100   # negative = below high
    pct_from_low  = (price - low_52w)  / low_52w  * 100   # positive = above low

    # Moving averages
    ma50  = float(close.tail(50).mean())  if len(close) >= 50  else None
    ma200 = float(close.tail(200).mean()) if len(close) >= 200 else None
    pct_from_ma200 = (price - ma200) / ma200 * 100 if ma200 else None

    # RSI(14)
    rsi = _calc_rsi(close)

    # Volume
    volume  = float(df["Volume"].iloc[-1])  if "Volume" in df.columns else None
    avg_vol = float(df["Volume"].tail(20).mean()) if "Volume" in df.columns and len(df) >= 20 else None

    return {
        "price":          price,
        "change":         change,
        "freshness":      freshness,
        "age_h":          age_h,
        "volume":         volume,
        "avg_vol":        avg_vol,
        "high_52w":       high_52w,
        "low_52w":        low_52w,
        "pct_from_high":  pct_from_high,
        "pct_from_low":   pct_from_low,
        "ma50":           ma50,
        "ma200":          ma200,
        "pct_from_ma200": pct_from_ma200,
        "rsi":            rsi,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def _ticker_short(ticker: str) -> dict:
    """Read short interest from disk cache — fetches from yfinance if stale."""
    if ticker.upper().endswith(("-USD", "-USDT")):
        return {"short_pct": None, "days_to_cover": None, "mom_change": None}
    try:
        from stonkslib.utils.short_interest import get_short_interest
        return get_short_interest(ticker)
    except Exception:
        return {"short_pct": None, "days_to_cover": None, "mom_change": None}


@st.cache_data(ttl=3600, show_spinner=False)
def _ticker_dividend(ticker: str) -> dict:
    if ticker.upper().endswith(("-USD", "-USDT")):
        return {"dividend_yield": None, "dividend_rate": None, "ex_date": None}
    try:
        from stonkslib.utils.dividends import get_dividends
        return get_dividends(ticker)
    except Exception:
        return {"dividend_yield": None, "dividend_rate": None, "ex_date": None}


@st.cache_data(ttl=3600, show_spinner=False)
def _ticker_earnings(ticker: str) -> dict:
    """Read next earnings date from disk cache only — never triggers a network fetch."""
    path = _EARNINGS_DIR / f"{ticker}.json"
    if not path.exists():
        return {"next_date": None, "days": None}
    try:
        with open(path) as f:
            raw = json.load(f)
        nd = raw.get("next_date")
        if not nd:
            return {"next_date": None, "days": None}
        next_dt = date.fromisoformat(nd[:10])
        days = (next_dt - date.today()).days
        return {"next_date": next_dt, "days": days}
    except Exception:
        return {"next_date": None, "days": None}




# ── load watchlist ────────────────────────────────────────────────────────────

wl = load_watchlist()

all_tickers = [t for items in wl.values() for t in (items or [])]
if not all_tickers:
    st.info("Watchlist is empty. Add tickers below.")
else:
    # summary strip
    rows_data = {t: _ticker_row(t) for t in all_tickers}
    fresh_counts = {}
    for d in rows_data.values():
        fresh_counts[d["freshness"]] = fresh_counts.get(d["freshness"], 0) + 1

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total tickers", len(all_tickers))
    m2.metric("Fresh",   fresh_counts.get("Fresh",   0))
    m3.metric("Stale",   fresh_counts.get("Stale",   0))
    m4.metric("Old",     fresh_counts.get("Old",     0))
    m5.metric("Missing", fresh_counts.get("Missing", 0))

    sc1, sc2 = st.columns([1, 5])
    with sc1:
        if st.button("🔄 Refresh", help="Clears the price cache so the next load re-reads parquet files"):
            st.cache_data.clear()
            st.rerun()
    with sc2:
        sort_by = st.selectbox(
            "Sort by",
            ["Default", "A → Z", "Day Change ▲", "Day Change ▼",
             "Signal", "Earnings Soon",
             "RSI Oversold ↓", "RSI Overbought ↑",
             "52W Low %", "52W High %",
             "Volume Ratio", "Short Interest ↓",
             "Div Yield ↓", "Ex-Date Soon"],
            key="wl_sort",
            label_visibility="collapsed",
        )

    st.divider()

    # ── pull alert results — session state first, fall back to disk cache ────
    if "alert_results" not in st.session_state:
        cached = load_alert_cache()
        if cached:
            st.session_state["alert_results"]  = cached["results"]
            st.session_state["alert_ts"]       = cached["ts"]
            st.session_state["alert_interval"] = cached["interval"]
            st.session_state["alert_min"]      = cached["min_signals"]

    alert_results: dict = st.session_state.get("alert_results", {})
    alert_ts    = st.session_state.get("alert_ts", "")
    alert_intv  = st.session_state.get("alert_interval", "")

    if alert_results:
        st.caption(f"Signals from last Alerts scan · **{alert_intv}** · {alert_ts}")
    else:
        st.caption("Signal column shows — until you run a scan on the **Alerts** page.")

    def _signal_text(ticker: str) -> str:
        if not alert_results or ticker not in alert_results:
            return "—"
        sigs = alert_results[ticker].get("signals", [])
        if not sigs:
            return "—"
        types = {s["type"] for s in sigs}
        if types == {"BUY"}:  return "▲ BUY"
        if types == {"SELL"}: return "▼ SELL"
        return "⚡ Mixed"

    def _signal_rank(ticker: str) -> int:
        t = _signal_text(ticker)
        return {"▲ BUY": 0, "⚡ Mixed": 1, "▼ SELL": 2}.get(t, 3)

    def _earnings_text(ticker: str) -> str:
        e = _ticker_earnings(ticker)
        nd   = e.get("next_date")
        days = e.get("days")
        if nd is None:
            return "—"
        date_str = nd.strftime("%b %-d")
        if days is None or days < 0:
            return date_str
        return f"{date_str} · {days}d"

    def _sort_key(ticker: str):
        d         = rows_data.get(ticker, {})
        e         = _ticker_earnings(ticker)
        si        = _ticker_short(ticker)
        div       = _ticker_dividend(ticker)
        change    = d.get("change")
        vol       = d.get("volume")
        avg_vol   = d.get("avg_vol")
        days      = e.get("days")
        short_pct = si.get("short_pct")
        div_yield = div.get("dividend_yield")
        vol_ratio = (vol / avg_vol) if (vol and avg_vol and avg_vol > 0) else 0

        ex_days = 9999
        if div.get("ex_date"):
            try:
                ex_days = (date.fromisoformat(div["ex_date"]) - date.today()).days
            except Exception:
                pass

        if sort_by == "A → Z":            return ticker
        if sort_by == "Day Change ▲":     return -(change   if change   is not None else -9999)
        if sort_by == "Day Change ▼":     return  (change   if change   is not None else  9999)
        if sort_by == "Signal":           return _signal_rank(ticker)
        if sort_by == "Earnings Soon":    return (days if (days is not None and days >= 0) else 9999)
        if sort_by == "RSI Oversold ↓":  return  (d.get("rsi") if d.get("rsi") is not None else  9999)
        if sort_by == "RSI Overbought ↑": return -(d.get("rsi") if d.get("rsi") is not None else -9999)
        if sort_by == "52W Low %":        return  (d.get("pct_from_low")  if d.get("pct_from_low")  is not None else  9999)
        if sort_by == "52W High %":       return  (d.get("pct_from_high") if d.get("pct_from_high") is not None else -9999)
        if sort_by == "Volume Ratio":     return -vol_ratio
        if sort_by == "Short Interest ↓": return -(short_pct if short_pct is not None else 0)
        if sort_by == "Div Yield ↓":     return -(div_yield if div_yield is not None else 0)
        if sort_by == "Ex-Date Soon":     return (ex_days if ex_days >= 0 else 9999)
        return 0

    # ── render each category as a dataframe table ─────────────────────────────
    for cat in VALID_CATEGORIES:
        items = wl.get(cat, []) or []
        if not items:
            continue

        if sort_by != "Default":
            items = sorted(items, key=_sort_key)

        st.subheader(f"{cat.capitalize()}  ({len(items)})")

        # build rows
        table_rows = []
        for ticker in items:
            d       = rows_data.get(ticker, {})
            price   = d.get("price")
            change  = d.get("change")
            vol     = d.get("volume")
            avg_vol = d.get("avg_vol")
            rsi     = d.get("rsi")
            p_low   = d.get("pct_from_low")
            p_high  = d.get("pct_from_high")
            p_ma200 = d.get("pct_from_ma200")
            high_52 = d.get("high_52w")
            low_52  = d.get("low_52w")
            fresh   = d.get("freshness", "Missing")

            # 52W range position: 0 = at 52W low, 100 = at 52W high
            if price and high_52 and low_52 and high_52 != low_52:
                range_pos = max(0.0, min(100.0, (price - low_52) / (high_52 - low_52) * 100))
            else:
                range_pos = None

            vol_ratio = (vol / avg_vol) if (vol and avg_vol and avg_vol > 0) else None

            si = _ticker_short(ticker)
            short_pct   = si.get("short_pct")
            days_cover  = si.get("days_to_cover")
            short_pct_display = short_pct * 100 if short_pct is not None else None

            div = _ticker_dividend(ticker)
            div_yield_display = (div["dividend_yield"] * 100
                                 if div.get("dividend_yield") else None)
            div_rate    = div.get("dividend_rate")
            ex_date_str = "—"
            if div.get("ex_date"):
                try:
                    ex_dt   = date.fromisoformat(div["ex_date"])
                    ex_days = (ex_dt - date.today()).days
                    ex_date_str = (f"{ex_dt.strftime('%b %-d')} · {ex_days}d"
                                   if ex_days >= 0 else ex_dt.strftime("%b %-d"))
                except Exception:
                    pass

            table_rows.append({
                "Ticker":    ticker,
                "Price":     price,
                "Chg %":     change,
                "Signal":    _signal_text(ticker),
                "RSI":       rsi,
                "52W Range": range_pos,
                "vs 200MA":  p_ma200,
                "Vol ×avg":  vol_ratio,
                "Div Yield": div_yield_display,
                "Div/Yr":    div_rate,
                "Ex-Date":   ex_date_str,
                "Short %":   short_pct_display,
                "Days Cvr":  days_cover,
                "Earnings":  _earnings_text(ticker),
                "Data":      fresh,
            })

        df_cat = pd.DataFrame(table_rows)

        col_cfg = {
            "Ticker":    st.column_config.TextColumn("Ticker",    width="small"),
            "Price":     st.column_config.NumberColumn("Price",   format="$%.2f",  width="small"),
            "Chg %":     st.column_config.NumberColumn("Chg %",   format="%.2f%%", width="small"),
            "Signal":    st.column_config.TextColumn("Signal",    width="small"),
            "RSI":       st.column_config.ProgressColumn(
                             "RSI", min_value=0, max_value=100, format="%.0f", width="small",
                             help="< 30 oversold  ·  > 70 overbought"),
            "52W Range": st.column_config.ProgressColumn(
                             "52W Range", min_value=0, max_value=100, format="%.0f%%", width="medium",
                             help="0% = at 52-week low  ·  100% = at 52-week high"),
            "vs 200MA":  st.column_config.NumberColumn("vs 200MA", format="%.1f%%", width="small"),
            "Vol ×avg":  st.column_config.NumberColumn("Vol ×avg", format="%.1f×",  width="small"),
            "Div Yield": st.column_config.NumberColumn("Div Yield", format="%.2f%%", width="small",
                             help="Annual dividend yield"),
            "Div/Yr":    st.column_config.NumberColumn("Div/Yr",   format="$%.2f",  width="small",
                             help="Annual dividend per share"),
            "Ex-Date":   st.column_config.TextColumn("Ex-Date",    width="small",
                             help="Next ex-dividend date — must own shares before this date to receive dividend"),
            "Short %":   st.column_config.NumberColumn("Short %",  format="%.1f%%", width="small",
                             help="% of float sold short  ·  >15% = elevated  ·  >25% = high squeeze risk"),
            "Days Cvr":  st.column_config.NumberColumn("Days Cvr", format="%.1f",   width="small",
                             help="Days to cover = shares short ÷ avg daily volume"),
            "Earnings":  st.column_config.TextColumn("Earnings",   width="small"),
            "Data":      st.column_config.TextColumn("Data",       width="small"),
        }

        event = st.dataframe(
            df_cat,
            column_config=col_cfg,
            use_container_width=True,
            hide_index=True,
            selection_mode="multi-row",
            on_select="rerun",
            key=f"wl_table_{cat}",
        )

        selected = event.selection.rows
        if selected:
            to_remove = [df_cat.iloc[i]["Ticker"] for i in selected]
            label = f"Remove {', '.join(to_remove)}"
            if st.button(label, type="secondary", key=f"rm_btn_{cat}"):
                wl2 = load_watchlist()
                for t in to_remove:
                    for c, lst in wl2.items():
                        if lst and t in lst:
                            lst.remove(t)
                save_watchlist(wl2)
                st.cache_data.clear()
                st.rerun()

        st.write("")

st.divider()

# ── add ticker ────────────────────────────────────────────────────────────────

st.subheader("Add Ticker")
col1, col2, col3 = st.columns([3, 2, 2])
with col1:
    new_ticker = st.text_input("Symbol", placeholder="e.g. AMD or SOL-USD").strip().upper()
with col2:
    new_cat = st.selectbox("Category", VALID_CATEGORIES)
with col3:
    st.write("")
    st.write("")
    add = st.button("Add + Fetch Data", type="primary", use_container_width=True)

if add:
    if not new_ticker:
        st.warning("Enter a ticker symbol.")
    else:
        wl2 = load_watchlist()
        wl2.setdefault(new_cat, [])
        if new_ticker in wl2.get(new_cat, []):
            st.warning(f"{new_ticker} is already in {new_cat}.")
        else:
            wl2[new_cat].append(new_ticker)
            save_watchlist(wl2)
            with st.status(f"Fetching data for {new_ticker}...", expanded=True) as s:
                # --no-analyze: stop at the cleaned parquet (fast). Indicator/pattern
                # analysis (only the Confluence page needs it) runs in the nightly
                # pipeline, or on demand from the Pipeline page.
                proc = subprocess.Popen(
                    [str(STONKS_BIN), "pipeline", new_ticker, "--no-analyze"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                )
                log = st.empty()
                lines = []
                for raw in proc.stdout:
                    line = raw.rstrip()
                    if line:
                        lines.append(line)
                        log.code("\n".join(lines[-20:]), language="text")
                proc.wait()
                if proc.returncode == 0:
                    s.update(label=f"✓ {new_ticker} data fetched", state="complete", expanded=False)
                    st.success(f"Added **{new_ticker}** to {new_cat}. "
                               f"(Confluence analysis runs in the nightly pipeline or via the Pipeline page.)")
                else:
                    s.update(label=f"✗ Fetch failed for {new_ticker}", state="error")
            st.cache_data.clear()
            st.rerun()
