"""
Earnings data loader — hybrid fetch: yfinance for deep history,
Finnhub for recent quarters (last 4) and upcoming date.

Cache location: data/ticker_data/earnings/{ticker}.json
TTL: 24 hours (re-fetches once per day at most).
"""

import json
import logging
import os
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

import time
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EARNINGS_DIR = PROJECT_ROOT / "data" / "ticker_data" / "earnings"
CACHE_TTL_HOURS = 24
_FINNHUB_BASE = "https://finnhub.io/api/v1"
_FINNHUB_MIN_INTERVAL = 1.1  # seconds between calls — free tier is 60/min
_last_finnhub_call: float = 0.0


def _cache_path(ticker: str) -> Path:
    return EARNINGS_DIR / f"{ticker}.json"


def _is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    age = datetime.now(timezone.utc) - datetime.fromtimestamp(
        path.stat().st_mtime, tz=timezone.utc
    )
    return age < timedelta(hours=CACHE_TTL_HOURS)


def _finnhub_get(path: str, params: dict) -> dict | list:
    global _last_finnhub_call
    api_key = os.getenv("FINNHUB_API_KEY", "")
    if not api_key:
        raise ValueError("FINNHUB_API_KEY not set in .env")
    elapsed = time.monotonic() - _last_finnhub_call
    if elapsed < _FINNHUB_MIN_INTERVAL:
        time.sleep(_FINNHUB_MIN_INTERVAL - elapsed)
    params["token"] = api_key
    resp = requests.get(f"{_FINNHUB_BASE}{path}", params=params, timeout=10)
    _last_finnhub_call = time.monotonic()
    resp.raise_for_status()
    return resp.json()


def _fetch(ticker: str) -> dict:
    """
    Fetch earnings from two sources:
      - yfinance: deep history (years of exact announcement dates + EPS)
      - Finnhub:  last 4 quarters (fills yfinance's ~1-year lag) + upcoming date
    """
    today = date.today()
    today_utc = datetime.now(timezone.utc)
    history_rows: list[dict] = []

    # ── 1. yfinance: deep history ─────────────────────────────────────────────
    yf_cutoff: date | None = None  # oldest Finnhub quarter we'll cover
    try:
        import yfinance as yf
        import warnings
        warnings.filterwarnings("ignore")
        t = yf.Ticker(ticker)
        # limit=40 covers ~10 years; default 12 drops recent quarters
        ed = t.get_earnings_dates(limit=40)
        if ed is not None and not ed.empty:
            past = ed[ed.index <= today_utc]
            for ts, row in past.iterrows():
                d = ts.date()
                if yf_cutoff is None or d > yf_cutoff:
                    yf_cutoff = d
                history_rows.append({
                    "date":         d.isoformat(),
                    "eps_estimate": _float(row.get("EPS Estimate")),
                    "reported_eps": _float(row.get("Reported EPS")),
                    "surprise_pct": _float(row.get("Surprise(%)")),
                })
    except Exception as e:
        logger.warning(f"[{ticker}] yfinance earnings failed: {e}")

    # ── 2. Finnhub stock/earnings: last 4 quarters ───────────────────────────
    # yfinance lags ~4 quarters behind; Finnhub covers that gap.
    finnhub_dates: set[date] = set()
    try:
        recent = _finnhub_get("/stock/earnings", {"symbol": ticker})
        if isinstance(recent, list):
            for entry in recent:
                period = entry.get("period", "")
                if not period:
                    continue
                qend = date.fromisoformat(period[:10])
                # approximate announcement ≈ fiscal quarter-end + 30 days
                approx = qend + timedelta(days=30)
                if approx > today:
                    continue
                # skip if yfinance already has an entry within 45 days
                if any(abs((approx - date.fromisoformat(r["date"])).days) < 45
                       for r in history_rows):
                    continue
                surprise_pct = _float(entry.get("surprisePercent"))
                history_rows.append({
                    "date":         approx.isoformat(),
                    "eps_estimate": _float(entry.get("estimate")),
                    "reported_eps": _float(entry.get("actual")),
                    "surprise_pct": surprise_pct,
                })
                finnhub_dates.add(approx)
    except Exception as e:
        logger.warning(f"[{ticker}] Finnhub stock/earnings failed: {e}")

    # Refine approximate Finnhub dates with exact calendar dates where available
    try:
        cal_past = _finnhub_get("/calendar/earnings", {
            "symbol": ticker,
            "from": (today - timedelta(days=400)).isoformat(),
            "to": today.isoformat(),
        })
        for cal_entry in cal_past.get("earningsCalendar", []):
            exact = date.fromisoformat(cal_entry["date"][:10])
            # find matching approximate entry (within 45 days) and update its date
            for row in history_rows:
                approx = date.fromisoformat(row["date"])
                if approx in finnhub_dates and abs((exact - approx).days) < 45:
                    row["date"] = exact.isoformat()
                    break
    except Exception as e:
        logger.warning(f"[{ticker}] Finnhub calendar (past) failed: {e}")

    # ── 3. Finnhub calendar: upcoming earnings ────────────────────────────────
    next_date = next_eps = next_rev = None
    try:
        cal_future = _finnhub_get("/calendar/earnings", {
            "symbol": ticker,
            "from": today.isoformat(),
            "to": (today + timedelta(days=180)).isoformat(),
        })
        for cal_entry in sorted(
            cal_future.get("earningsCalendar", []), key=lambda x: x["date"]
        ):
            next_date = cal_entry["date"][:10]
            next_eps  = _float(cal_entry.get("epsEstimate"))
            next_rev  = _float(cal_entry.get("revenueEstimate"))
            break
    except Exception as e:
        logger.warning(f"[{ticker}] Finnhub calendar (future) failed: {e}")

    history_rows.sort(key=lambda r: r["date"], reverse=True)

    return {
        "ticker":                ticker,
        "fetched_at":            datetime.now(timezone.utc).isoformat(),
        "next_date":             next_date,
        "next_eps_estimate":     next_eps,
        "next_revenue_estimate": next_rev,
        "history":               history_rows,
    }


def _float(v):
    try:
        return float(v) if v is not None and str(v) not in ("nan", "None", "") else None
    except Exception:
        return None


def _save(ticker: str, data: dict):
    EARNINGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(_cache_path(ticker), "w") as f:
        json.dump(data, f, indent=2)


def _load_cache(ticker: str) -> dict | None:
    path = _cache_path(ticker)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def get_earnings(ticker: str, force_refresh: bool = False) -> dict:
    """
    Returns earnings data for a ticker. Loads from disk cache if fresh,
    otherwise fetches and saves.

    Return structure:
        next_date             — date or None
        next_eps_estimate     — float or None
        next_revenue_estimate — float or None
        history               — pd.DataFrame (index=date, cols: eps_estimate,
                                reported_eps, surprise_pct)
    """
    path = _cache_path(ticker)

    if not force_refresh and _is_fresh(path):
        raw = _load_cache(ticker)
    else:
        logger.info(f"[{ticker}] Fetching earnings")
        try:
            raw = _fetch(ticker)
            _save(ticker, raw)
        except Exception as e:
            logger.error(f"[{ticker}] Earnings fetch failed: {e}")
            raw = _load_cache(ticker) or {}

    rows = raw.get("history", [])
    if rows:
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index(ascending=False)
    else:
        df = pd.DataFrame(columns=["eps_estimate", "reported_eps", "surprise_pct"])

    next_date = None
    if raw.get("next_date"):
        try:
            next_date = date.fromisoformat(raw["next_date"][:10])
        except Exception:
            pass

    return {
        "history":               df,
        "next_date":             next_date,
        "next_eps_estimate":     raw.get("next_eps_estimate"),
        "next_revenue_estimate": raw.get("next_revenue_estimate"),
    }


def fetch_and_save(ticker: str) -> dict:
    """Force-refresh earnings and save to disk. Used by pipeline."""
    raw = _fetch(ticker)
    _save(ticker, raw)
    logger.info(f"[{ticker}] Earnings saved → {_cache_path(ticker)}")
    return raw
