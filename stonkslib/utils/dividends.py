"""
Dividend data fetcher — uses yfinance ticker.info.

Dividends change quarterly at most; cache TTL is 24 hours.
Cache location: data/ticker_data/dividends/{ticker}.json
"""

import json
import logging
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)

PROJECT_ROOT  = Path(__file__).resolve().parents[2]
DIVIDEND_DIR  = PROJECT_ROOT / "data" / "ticker_data" / "dividends"
CACHE_TTL_HOURS = 24


def _cache_path(ticker: str) -> Path:
    return DIVIDEND_DIR / f"{ticker}.json"


def _is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    age = datetime.now(timezone.utc) - datetime.fromtimestamp(
        path.stat().st_mtime, tz=timezone.utc
    )
    return age < timedelta(hours=CACHE_TTL_HOURS)


def _float(v):
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def _to_date(ts) -> str | None:
    """Convert a yfinance timestamp (int, float, or ISO string) to an ISO date string."""
    if ts is None:
        return None
    try:
        return date.fromtimestamp(int(ts)).isoformat()
    except Exception:
        pass
    try:
        return date.fromisoformat(str(ts)[:10]).isoformat()
    except Exception:
        return None


def _fetch(ticker: str) -> dict:
    import yfinance as yf
    import warnings
    warnings.filterwarnings("ignore")

    t    = yf.Ticker(ticker)
    info = t.info or {}

    # dividendYield: yfinance may return a fraction (0.033) or a percentage (3.3)
    # — normalise to fraction so callers always get 0-1
    yield_ = _float(info.get("dividendYield"))
    if yield_ is not None and yield_ > 1.0:
        yield_ /= 100

    rate   = _float(info.get("dividendRate"))   # annual $ per share
    payout = _float(info.get("payoutRatio"))

    # ex-dividend date — try multiple keys yfinance uses inconsistently
    ex_date = (
        _to_date(info.get("exDividendDate"))
        or _to_date(info.get("lastDividendDate"))
    )

    # if info fields are missing, fall back to dividend history
    if rate is None or ex_date is None:
        try:
            hist = t.dividends
            if not hist.empty:
                if rate is None:
                    # annualise last 12 months of payments
                    cutoff = hist.index[-1] - pd.DateOffset(years=1)
                    ttm = hist[hist.index >= cutoff]
                    rate = round(float(ttm.sum()), 4) if not ttm.empty else None
                if ex_date is None:
                    ex_date = hist.index[-1].date().isoformat()
        except Exception:
            pass

    return {
        "ticker":         ticker,
        "fetched_at":     datetime.now(timezone.utc).isoformat(),
        "dividend_yield": yield_,   # fraction 0-1, e.g. 0.033 = 3.3%
        "dividend_rate":  rate,     # annual $ per share
        "payout_ratio":   payout,
        "ex_date":        ex_date,  # ISO date string or None
    }


def get_dividends(ticker: str, force_refresh: bool = False) -> dict:
    """
    Returns dividend data for a ticker.
    Loads from disk if fresh (< 24h), otherwise fetches from yfinance.
    Skips crypto (tickers ending in -USD / -USDT) — returns empty dict.

    Return keys:
        dividend_yield  — float 0-1 (e.g. 0.015 = 1.5%), or None
        dividend_rate   — annual $ per share, or None
        payout_ratio    — fraction, or None
        ex_date         — ISO date string of next ex-dividend date, or None
    """
    _empty = {"ticker": ticker, "dividend_yield": None,
              "dividend_rate": None, "payout_ratio": None, "ex_date": None}

    if ticker.upper().endswith(("-USD", "-USDT")):
        return _empty

    path = _cache_path(ticker)

    if not force_refresh and _is_fresh(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass

    logger.info(f"[{ticker}] Fetching dividend data")
    try:
        data = _fetch(ticker)
        DIVIDEND_DIR.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return data
    except Exception as e:
        logger.warning(f"[{ticker}] Dividend fetch failed: {e}")
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                pass
        return _empty


def fetch_and_save(ticker: str) -> dict:
    """Force-refresh dividend data. Used by earnings-refresh timer."""
    return get_dividends(ticker, force_refresh=True)
