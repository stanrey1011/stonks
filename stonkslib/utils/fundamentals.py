"""Compact fundamentals / valuation snapshot via yfinance `.info`.

Cache location: data/ticker_data/fundamentals/{ticker}.json   TTL: 24h.
Mirrors utils/dividends.py. Feeds the Analyst dashboard / analyst agent — a small,
stable subset of yfinance's noisy `.info` rather than the whole blob.
"""

import json
import logging
import warnings
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FUND_DIR = PROJECT_ROOT / "data" / "ticker_data" / "fundamentals"
CACHE_TTL_HOURS = 24


def _cache_path(ticker: str) -> Path:
    return FUND_DIR / f"{ticker}.json"


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
    except (TypeError, ValueError):
        return None


def _is_crypto(ticker: str) -> bool:
    return ticker.endswith("-USD") or ticker.endswith("-USDT")


def _fetch(ticker: str) -> dict:
    import yfinance as yf
    warnings.filterwarnings("ignore")
    info = yf.Ticker(ticker).info or {}

    pm = _float(info.get("profitMargins"))
    rg = _float(info.get("revenueGrowth"))
    return {
        "ticker":         ticker,
        "fetched_at":     datetime.now(timezone.utc).isoformat(),
        "name":           info.get("shortName") or info.get("longName"),
        "sector":         info.get("sector"),
        "industry":       info.get("industry"),
        "market_cap":     _float(info.get("marketCap")),
        "trailing_pe":    _float(info.get("trailingPE")),
        "forward_pe":     _float(info.get("forwardPE")),
        "eps_ttm":        _float(info.get("trailingEps")),
        "beta":           _float(info.get("beta")),
        "week52_high":    _float(info.get("fiftyTwoWeekHigh")),
        "week52_low":     _float(info.get("fiftyTwoWeekLow")),
        "profit_margin":  pm,                       # fraction 0-1
        "revenue_growth": rg,                       # fraction (yoy)
        "target_mean":    _float(info.get("targetMeanPrice")),
        "recommendation": info.get("recommendationKey"),   # e.g. "buy", "hold"
    }


def get_fundamentals(ticker: str, force_refresh: bool = False) -> dict:
    """Return a compact fundamentals snapshot for a ticker (empty dict for crypto).

    Loads from disk if fresh (< 24h), otherwise fetches from yfinance. Never raises —
    returns whatever it has (possibly {}) on error.
    """
    if _is_crypto(ticker):
        return {}

    path = _cache_path(ticker)
    if not force_refresh and _is_fresh(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass

    try:
        data = _fetch(ticker)
        FUND_DIR.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return data
    except Exception as e:
        logger.warning(f"[{ticker}] fundamentals fetch failed: {e}")
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}


def fetch_and_save(ticker: str) -> dict:
    """Force-refresh fundamentals and save to disk."""
    return get_fundamentals(ticker, force_refresh=True)
