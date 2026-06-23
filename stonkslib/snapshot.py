"""Unified ticker data spine — `hydrate(ticker)` returns one `TickerSnapshot`.

Every consumer (dashboard pages, the multi-agent fund, the CLI) imports
`hydrate()` instead of independently querying the ~7 data directories the app
writes to. This is the single source of truth for "what do we know about NVDA
right now?", with a per-source freshness stamp so the caller can tell whether to
trust each number.

Design rules:
- Each section is independently guarded (try/except per source) — one failed
  source never blanks the rest.
- The **confluence** section comes from the *live* strategy engine
  (`build_namespace` / `vote_signals` / `confluence_scores`), NOT pre-saved
  signal CSVs, so the votes match exactly what the backtester sees (incl. the
  LLM `news_sent` vote).
- The **edge** section reads cached backtest `*_metrics.json` for both regular
  (swing) strategies and LEAP strategies, so the portfolio-manager agent can
  bucket its verdict by vehicle (LEAP / DCA / Swing).

See `docs/snapshot-schema.md` for the full field-by-field contract, and
`docs/stonks-advisor-handoff.md` for the original design.
"""

from __future__ import annotations

import glob
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from stonkslib.indicators.registry import INDICATORS
from stonkslib.strategies.engine import (
    build_namespace,
    confluence_scores,
    vote_signals,
)
from stonkslib.utils.load_td import load_td

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA = PROJECT_ROOT / "data"
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"

CLEAN_DIR = DATA / "ticker_data" / "clean"
FUND_DIR = DATA / "ticker_data" / "fundamentals"
EARNINGS_DIR = DATA / "ticker_data" / "earnings"
NEWS_DIR = DATA / "ticker_data" / "news"
SHORT_DIR = DATA / "ticker_data" / "short"
BACKTEST_STRATEGY = DATA / "backtest_results" / "strategy"
BACKTEST_LEAPS = DATA / "backtest_results" / "leaps"

# Indicators surfaced in the confluence pane (registry keys, in display order).
TA_INDICATORS = ["rsi", "macd", "bollinger", "supertrend", "markov", "news_sentiment"]
# Namespace outputs worth exposing as "latest reading" values.
TA_READOUTS = ["close", "rsi", "macd", "macd_signal", "st_dir", "mk_bull", "mk_bear", "news_sent"]

# A strategy "has edge" when it clears all three floors. Configurable here.
MIN_WIN_RATE = 0.50
MIN_TRADES = 5

# Per-source freshness TTLs in hours. Beyond the TTL a source is marked stale.
TTL_HOURS = {
    "price": 24,
    "fundamentals": 48,
    "earnings": 48,
    "news": 8,
    "short_interest": 96,
    "backtest": 24 * 7,
}


# ── small helpers ──────────────────────────────────────────────────────────────

def _last(series) -> float | None:
    """Last non-NaN value of a Series as float, or None."""
    if series is None or len(series) == 0:
        return None
    v = series.iloc[-1]
    return None if pd.isna(v) else float(v)


def _col(df: pd.DataFrame, name: str):
    """Case-insensitive column access — `load_td` title-cases columns
    (Close/High/Low/Volume), so look the name up regardless of case."""
    for c in (name, name.title(), name.capitalize(), name.upper(), name.lower()):
        if c in df.columns:
            return df[c]
    return None


def _mtime(path: Path) -> datetime | None:
    """File modified time as tz-aware UTC datetime, or None if absent."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except (FileNotFoundError, OSError):
        return None


def _freshness(updated_at: datetime | None, ttl_hours: int) -> dict:
    """{updated_at, stale} for one source given its file mtime and TTL."""
    if updated_at is None:
        return {"updated_at": None, "stale": True}
    age_h = (datetime.now(timezone.utc) - updated_at).total_seconds() / 3600
    return {"updated_at": updated_at.isoformat(), "stale": age_h > ttl_hours}


def _newest_mtime(pattern: str) -> datetime | None:
    """Newest mtime among files matching a glob pattern, or None."""
    times = [_mtime(Path(p)) for p in glob.glob(pattern)]
    times = [t for t in times if t is not None]
    return max(times) if times else None


# ── confluence (live engine) ────────────────────────────────────────────────────

def _engine_run(df: pd.DataFrame, keys: list[str]):
    """Run the engine for a set of indicator keys → (strategy, ns, votes, buy, sell)."""
    strategy = {"indicators": {k: {} for k in keys if k in INDICATORS}}
    ns = build_namespace(df, strategy)
    votes = vote_signals(df, strategy, ns)
    buy, sell = confluence_scores(df, strategy, ns)
    return strategy, ns, votes, buy, sell


def _confluence(df: pd.DataFrame, ticker: str) -> dict:
    """Latest-bar indicator votes + readings + weighted confluence, via the engine.

    Pins the signal source of truth to the same code path the backtester uses.
    Degrades gracefully: if an optional indicator that needs external infra fails
    (e.g. `news_sentiment` can't reach the sentiment DB), the core technical read
    (RSI/MACD/Bollinger/Supertrend/Markov) is preserved rather than lost wholesale.
    """
    df = df.copy()
    df.attrs["ticker"] = ticker  # lets the news_sentiment indicator resolve scores

    keys = [k for k in TA_INDICATORS if k in INDICATORS]
    degraded = []
    try:
        strategy, ns, votes, buy, sell = _engine_run(df, keys)
    except Exception as e:
        # Retry without optional external-dependency indicators.
        core = [k for k in keys if k != "news_sentiment"]
        logger.warning("[snapshot] confluence full set failed (%s); retrying core only", e)
        strategy, ns, votes, buy, sell = _engine_run(df, core)
        degraded = [k for k in keys if k not in core]

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

    return {
        "buy_score": round(_last(buy) or 0.0, 3),
        "sell_score": round(_last(sell) or 0.0, 3),
        "votes": rows,
        "readouts": {name: _last(ns.get(name)) for name in TA_READOUTS if name in ns},
        "asof": str(df.index[-1]),
        "degraded": degraded,  # indicators dropped due to infra failure, if any
    }


# ── edge (cached backtest metrics) ──────────────────────────────────────────────

def _summarize_strategies(entries: list[dict]) -> dict:
    """Apply the edge floors and pick the best qualifying strategy."""
    qualifying = [
        s for s in entries
        if (s.get("win_rate") or 0) >= MIN_WIN_RATE
        and (s.get("trades") or 0) >= MIN_TRADES
        and (s.get("net_pnl") or 0) > 0
    ]
    best = max(qualifying, key=lambda s: s["win_rate"] or 0) if qualifying else None
    return {"strategies": entries, "has_edge": bool(qualifying), "best": best}


def _swing_edge(ticker: str, interval: str) -> dict:
    """Regular strategy backtest metrics → swing-trade edge."""
    entries = []
    for path in sorted(glob.glob(str(BACKTEST_STRATEGY / ticker / interval / "*_metrics.json"))):
        try:
            with open(path) as f:
                m = json.load(f)
        except Exception:
            continue
        entries.append({
            "strategy": m.get("strategy", Path(path).stem.replace("_metrics", "")),
            "win_rate": m.get("win_rate"),
            "net_pnl": m.get("net_pnl"),
            "max_drawdown": m.get("max_drawdown"),
            "trades": m.get("trades"),
        })
    return _summarize_strategies(entries)


def _leap_edge(ticker: str, interval: str) -> dict:
    """LEAP backtest metrics → options edge, scored by avg_pnl_pct (per the LEAP design)."""
    entries = []
    for path in sorted(glob.glob(str(BACKTEST_LEAPS / ticker / interval / "*_metrics.json"))):
        try:
            with open(path) as f:
                m = json.load(f)
        except Exception:
            continue
        entries.append({
            "strategy": m.get("strategy", Path(path).stem.replace("_metrics", "")),
            "option_type": m.get("option_type"),
            "win_rate": m.get("win_rate"),
            "avg_pnl_pct": m.get("avg_pnl_pct"),
            "net_pnl": m.get("net_pnl"),
            "trades": m.get("trades"),
        })
    qualifying = [
        s for s in entries
        if (s.get("win_rate") or 0) >= MIN_WIN_RATE
        and (s.get("trades") or 0) >= MIN_TRADES
        and (s.get("avg_pnl_pct") or 0) > 0
    ]
    best = max(qualifying, key=lambda s: s.get("avg_pnl_pct") or 0) if qualifying else None
    return {"strategies": entries, "has_edge": bool(qualifying), "best": best}


# ── hydrate ─────────────────────────────────────────────────────────────────────

def hydrate(ticker: str, interval: str = "1d", news_days: int = 7) -> dict:
    """Assemble the full `TickerSnapshot` for one ticker.

    Every section is independently guarded — a single source failure (e.g. a
    yfinance hiccup) leaves that section as `{"error": ...}` but never blanks the
    rest of the snapshot.
    """
    ticker = ticker.upper()
    snap: dict = {
        "ticker": ticker,
        "interval": interval,
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
    }
    fresh: dict = {}

    # ── Price + confluence (both derive from the cleaned Parquet) ──────────────
    df = None
    try:
        df = load_td([ticker], interval).get(ticker)
    except Exception as e:
        snap["price"] = {"error": str(e)}
        snap["confluence"] = {"error": str(e)}
    if df is not None and not df.empty:
        try:
            closes = _col(df, "close")
            highs = _col(df, "high")
            lows = _col(df, "low")
            vols = _col(df, "volume")
            close = float(closes.iloc[-1])
            prev = float(closes.iloc[-2]) if len(closes) > 1 else None
            snap["price"] = {
                "close": close,
                "prev_close": prev,
                "day_change_pct": round((close / prev - 1) * 100, 2) if prev else None,
                "high_52w": float((highs if highs is not None else closes).tail(252).max()),
                "low_52w": float((lows if lows is not None else closes).tail(252).min()),
                "volume": float(vols.iloc[-1]) if vols is not None else None,
            }
        except Exception as e:
            snap["price"] = {"error": str(e)}
        try:
            snap["confluence"] = _confluence(df, ticker)
        except Exception as e:
            snap["confluence"] = {"error": str(e)}
    elif "price" not in snap:
        snap["price"] = {"error": "no price data"}
        snap["confluence"] = {"error": "no price data"}
    fresh["price"] = _freshness(_mtime(CLEAN_DIR / ticker / f"{interval}.parquet"), TTL_HOURS["price"])

    # ── Edge (swing + LEAP backtest metrics) ───────────────────────────────────
    try:
        snap["edge"] = _swing_edge(ticker, interval)
    except Exception as e:
        snap["edge"] = {"error": str(e)}
    try:
        snap["leap_edge"] = _leap_edge(ticker, interval)
    except Exception as e:
        snap["leap_edge"] = {"error": str(e)}
    fresh["backtest"] = _freshness(
        _newest_mtime(str(BACKTEST_STRATEGY / ticker / interval / "*_metrics.json")),
        TTL_HOURS["backtest"],
    )

    # ── Fundamentals ───────────────────────────────────────────────────────────
    try:
        from stonkslib.utils.fundamentals import get_fundamentals
        snap["fundamentals"] = get_fundamentals(ticker)
    except Exception as e:
        snap["fundamentals"] = {"error": str(e)}
    fresh["fundamentals"] = _freshness(_mtime(FUND_DIR / f"{ticker}.json"), TTL_HOURS["fundamentals"])

    # ── Dividends (matters for the DCA bucket) ─────────────────────────────────
    try:
        from stonkslib.utils.dividends import get_dividends
        snap["dividends"] = get_dividends(ticker)
    except Exception as e:
        snap["dividends"] = {"error": str(e)}

    # ── Earnings ───────────────────────────────────────────────────────────────
    try:
        from stonkslib.utils.earnings import get_earnings
        e = get_earnings(ticker)
        nd = e.get("next_date")
        # last_surprise lives in the history DataFrame (date-indexed, most-recent
        # first), not as a top-level key — derive it.
        hist = e.get("history")
        last_surprise = last_reported = None
        try:
            if hist is not None and len(hist) > 0:
                sp = hist.iloc[0].get("surprise_pct")
                last_surprise = None if pd.isna(sp) else float(sp)
                last_reported = str(hist.index[0])[:10]
        except Exception:
            pass
        snap["earnings"] = {
            "next_date": nd.isoformat() if hasattr(nd, "isoformat") else (str(nd) if nd else None),
            "next_eps_estimate": e.get("next_eps_estimate"),
            "last_surprise_pct": last_surprise,
            "last_reported_date": last_reported,
        }
    except Exception as e:
        snap["earnings"] = {"error": str(e)}
    fresh["earnings"] = _freshness(_mtime(EARNINGS_DIR / f"{ticker}.json"), TTL_HOURS["earnings"])

    # ── Sentiment (precomputed LLM scores + Finnhub's own) ─────────────────────
    finnhub_sent = {}
    try:
        from stonkslib.utils.news_store import load_sentiment_rows
        rows = load_sentiment_rows(ticker, limit=14)
        snap["sentiment"] = {"llm": rows, "latest": (rows[0]["score"] if rows else None)}
    except Exception as e:
        snap["sentiment"] = {"error": str(e)}

    # ── News (recent headlines + Finnhub sentiment strip) ──────────────────────
    try:
        from stonkslib.utils.news import get_news
        nd = get_news(ticker, days=news_days)
        finnhub_sent = nd.get("sentiment") or {}
        snap["news"] = {
            "articles": (nd.get("articles") or [])[:8],
            "finnhub": finnhub_sent,
        }
    except Exception as e:
        snap["news"] = {"error": str(e)}
    if isinstance(snap.get("sentiment"), dict) and "error" not in snap["sentiment"]:
        snap["sentiment"]["finnhub"] = finnhub_sent
    fresh["news"] = _freshness(_mtime(NEWS_DIR / f"{ticker}.json"), TTL_HOURS["news"])

    # ── Short interest ─────────────────────────────────────────────────────────
    try:
        from stonkslib.utils.short_interest import get_short_interest
        snap["short_interest"] = get_short_interest(ticker)
    except Exception as e:
        snap["short_interest"] = {"error": str(e)}
    fresh["short_interest"] = _freshness(_mtime(SHORT_DIR / f"{ticker}.json"), TTL_HOURS["short_interest"])

    snap["freshness"] = fresh
    return snap


# ── watchlist ───────────────────────────────────────────────────────────────────

def _watchlist(categories: tuple[str, ...] = ("stocks", "etfs")) -> list[str]:
    """Flat list of tickers from tickers.yaml. Crypto excluded by default."""
    try:
        with open(TICKER_YAML) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return []
    out: list[str] = []
    for cat in categories:
        out.extend(data.get(cat) or [])
    return out


def hydrate_watchlist(
    interval: str = "1d",
    categories: tuple[str, ...] = ("stocks", "etfs"),
    tickers: list[str] | None = None,
) -> list[dict]:
    """Hydrate every watchlist ticker. Returns a list of snapshots."""
    names = tickers or _watchlist(categories)
    out = []
    for t in names:
        try:
            out.append(hydrate(t, interval=interval))
        except Exception as e:
            logger.warning("[snapshot] hydrate failed for %s: %s", t, e)
    return out


if __name__ == "__main__":
    import sys
    tkr = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    print(json.dumps(hydrate(tkr), indent=2, default=str))
