"""
Short interest fetcher — uses yfinance ticker.info.

FINRA reports short interest twice a month, so data only changes every ~2 weeks.
Cache TTL is 72 hours; a fresh fetch runs at most once every 3 days per ticker.

Cache location: data/ticker_data/short/{ticker}.json
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHORT_DIR = PROJECT_ROOT / "data" / "ticker_data" / "short"
CACHE_TTL_HOURS = 72


def _cache_path(ticker: str) -> Path:
    return SHORT_DIR / f"{ticker}.json"


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


def _fetch(ticker: str) -> dict:
    import yfinance as yf
    import warnings
    warnings.filterwarnings("ignore")

    t = yf.Ticker(ticker)
    info = t.info or {}

    short_pct   = _float(info.get("shortPercentOfFloat"))
    days_cover  = _float(info.get("shortRatio"))
    shares_short = _float(info.get("sharesShort"))
    shares_prior = _float(info.get("sharesShortPriorMonth"))

    mom_change = None
    if shares_short and shares_prior and shares_prior > 0:
        mom_change = (shares_short - shares_prior) / shares_prior * 100

    return {
        "ticker":       ticker,
        "fetched_at":   datetime.now(timezone.utc).isoformat(),
        "short_pct":    short_pct,    # fraction of float (e.g. 0.15 = 15%)
        "days_to_cover": days_cover,  # shares short / avg daily volume
        "shares_short": shares_short,
        "shares_prior": shares_prior,
        "mom_change":   mom_change,   # % change vs prior month, positive = more shorting
    }


def get_short_interest(ticker: str, force_refresh: bool = False) -> dict:
    """
    Returns short interest data for a ticker.
    Loads from disk if fresh (< 72h), otherwise fetches from yfinance.

    Return keys:
        short_pct      — float 0-1 (e.g. 0.15 = 15% of float), or None
        days_to_cover  — float, or None
        shares_short   — float, or None
        mom_change     — % change vs prior month, or None
    """
    path = _cache_path(ticker)

    if not force_refresh and _is_fresh(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass

    logger.info(f"[{ticker}] Fetching short interest")
    try:
        data = _fetch(ticker)
        SHORT_DIR.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return data
    except Exception as e:
        logger.warning(f"[{ticker}] Short interest fetch failed: {e}")
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                pass
        return {"ticker": ticker, "short_pct": None, "days_to_cover": None,
                "shares_short": None, "mom_change": None}
