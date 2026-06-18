"""Analyst brief — the single data-gathering function behind the Analyst dashboard.

`analyst_brief(ticker)` assembles everything an analyst (human or, later, an LLM
analyst agent in the multi-agent setup) needs for one name: fundamentals, news
sentiment, recent headlines, and a technical read. The dashboard page renders this
dict; the future agent will call the same function for its context — one source of
truth, no duplicated gathering logic.

The technical read reuses the *real* strategy engine (build_namespace / vote_signals
/ confluence_scores) so the votes shown here match what the backtester would see,
including the LLM `news_sent` vote. Nothing here calls an LLM at request time — the
sentiment scores are read from the precomputed store.
"""

import pandas as pd

from stonkslib.indicators.registry import INDICATORS
from stonkslib.strategies.engine import build_namespace, vote_signals, confluence_scores
from stonkslib.utils.load_td import load_td

# The indicators surfaced in the TA pane (registry keys, in display order).
TA_INDICATORS = ["rsi", "macd", "bollinger", "supertrend", "markov", "news_sentiment"]

# Namespace outputs worth showing as "latest reading" values.
TA_READOUTS = ["close", "rsi", "macd", "macd_signal", "st_dir", "mk_bull", "mk_bear", "news_sent"]


def _last(series) -> float | None:
    """Last non-NaN value of a Series as float, or None."""
    if series is None or len(series) == 0:
        return None
    v = series.iloc[-1]
    return None if pd.isna(v) else float(v)


def _ta_summary(df: pd.DataFrame, ticker: str) -> dict:
    """Latest-bar indicator votes + readings + weighted confluence, via the engine."""
    df = df.copy()
    df.attrs["ticker"] = ticker  # so the news_sentiment indicator can resolve scores
    strategy = {"indicators": {k: {} for k in TA_INDICATORS if k in INDICATORS}}

    ns = build_namespace(df, strategy)
    votes = vote_signals(df, strategy, ns)
    buy, sell = confluence_scores(df, strategy, ns)

    rows = []
    for key in strategy["indicators"]:
        b = votes["BUY"].get(key)
        s = votes["SELL"].get(key)
        if b is not None and bool(b.iloc[-1]):
            vote = "BUY"
        elif s is not None and bool(s.iloc[-1]):
            vote = "SELL"
        else:
            vote = "—"
        rows.append({"indicator": key, "vote": vote})

    readouts = {name: _last(ns.get(name)) for name in TA_READOUTS if name in ns}
    return {
        "votes": rows,
        "readouts": readouts,
        "buy_score": _last(buy) or 0.0,
        "sell_score": _last(sell) or 0.0,
        "asof": str(df.index[-1]),
    }


def analyst_brief(ticker: str, interval: str = "1d", news_days: int = 7) -> dict:
    """Assemble the analyst brief for a ticker. Each pane is independently guarded —
    a failure in one (e.g. yfinance hiccup) never blanks the rest."""
    ticker = ticker.upper()
    brief: dict = {"ticker": ticker, "interval": interval}

    # ── Fundamentals (valuation snapshot + earnings + dividends) ──────────────
    try:
        from stonkslib.utils.fundamentals import get_fundamentals
        brief["fundamentals"] = get_fundamentals(ticker)
    except Exception as e:
        brief["fundamentals"] = {"error": str(e)}
    try:
        from stonkslib.utils.earnings import get_earnings
        e = get_earnings(ticker)
        nd = e.get("next_date")
        brief["earnings"] = {
            "next_date": nd.isoformat() if hasattr(nd, "isoformat") else (str(nd) if nd else None),
            "next_eps_estimate": e.get("next_eps_estimate"),
        }
    except Exception as e:
        brief["earnings"] = {"error": str(e)}
    try:
        from stonkslib.utils.dividends import get_dividends
        brief["dividends"] = get_dividends(ticker)
    except Exception as e:
        brief["dividends"] = {"error": str(e)}

    # ── Sentiment (precomputed LLM scores + Finnhub's own, if available) ──────
    try:
        from stonkslib.utils.news_store import load_sentiment_rows
        rows = load_sentiment_rows(ticker, limit=14)
        brief["sentiment"] = {"llm": rows, "latest": (rows[0]["score"] if rows else None)}
    except Exception as e:
        brief["sentiment"] = {"error": str(e)}

    # ── News (recent headlines + Finnhub sentiment strip) ─────────────────────
    try:
        from stonkslib.utils.news import get_news
        nd = get_news(ticker, days=news_days)
        brief["news"] = {
            "articles": (nd.get("articles") or [])[:12],
            "finnhub": nd.get("sentiment") or {},
        }
    except Exception as e:
        brief["news"] = {"error": str(e)}

    # ── Technical read (engine votes + confluence on the latest bar) ──────────
    try:
        df = load_td([ticker], interval).get(ticker)
        brief["ta"] = _ta_summary(df, ticker) if df is not None and not df.empty else {"error": "no price data"}
    except Exception as e:
        brief["ta"] = {"error": str(e)}

    return brief
