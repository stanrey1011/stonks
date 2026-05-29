"""
Finnhub news fetcher — company news articles + sentiment.

Cache location: data/ticker_data/news/{ticker}.json
TTL: 4 hours (news updates frequently).
"""

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NEWS_DIR = PROJECT_ROOT / "data" / "ticker_data" / "news"
CACHE_TTL_HOURS = 4

_FINNHUB_BASE = "https://finnhub.io/api/v1"
_FINNHUB_MIN_INTERVAL = 1.1
_last_finnhub_call: float = 0.0


def _cache_path(ticker: str) -> Path:
    return NEWS_DIR / f"{ticker}.json"


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


def _fetch(ticker: str, days: int = 14) -> dict:
    today = datetime.now(timezone.utc)
    from_date = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")

    articles = []
    try:
        raw = _finnhub_get("/company-news", {
            "symbol": ticker,
            "from": from_date,
            "to": to_date,
        })
        if isinstance(raw, list):
            seen_ids: set = set()
            for item in raw:
                aid = item.get("id")
                if aid and aid in seen_ids:
                    continue
                if aid:
                    seen_ids.add(aid)
                ts = item.get("datetime", 0)
                articles.append({
                    "datetime":  ts,
                    "date":      datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d") if ts else None,
                    "headline":  item.get("headline", ""),
                    "source":    item.get("source", ""),
                    "summary":   item.get("summary", ""),
                    "url":       item.get("url", ""),
                    "category":  item.get("category", ""),
                })
            articles.sort(key=lambda a: a["datetime"], reverse=True)
    except Exception as e:
        logger.warning(f"[{ticker}] Finnhub company-news failed: {e}")

    sentiment = {}
    try:
        raw_s = _finnhub_get("/news-sentiment", {"symbol": ticker})
        buzz = raw_s.get("buzz", {})
        sent = raw_s.get("sentiment", {})
        sentiment = {
            "bullish_pct":      sent.get("bullishPercent"),
            "bearish_pct":      sent.get("bearishPercent"),
            "buzz":             buzz.get("buzz"),
            "articles_week":    buzz.get("articlesInLastWeek"),
            "weekly_average":   buzz.get("weeklyAverage"),
            "company_score":    raw_s.get("companyNewsScore"),
            "sector_avg_score": raw_s.get("sectorAverageNewsScore"),
        }
    except Exception as e:
        logger.warning(f"[{ticker}] Finnhub news-sentiment failed: {e}")

    return {
        "ticker":     ticker,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "days":       days,
        "articles":   articles,
        "sentiment":  sentiment,
    }


def get_news(ticker: str, days: int = 14, force_refresh: bool = False) -> dict:
    """
    Returns news and sentiment for a ticker.
    Loads from disk cache if fresh (< 4h), otherwise fetches from Finnhub.

    Return structure:
        articles   — list of dicts: datetime, date, headline, source, summary, url, category
        sentiment  — dict: bullish_pct, bearish_pct, buzz, articles_week, weekly_average
        fetched_at — ISO datetime string
    """
    path = _cache_path(ticker)

    if not force_refresh and _is_fresh(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass

    logger.info(f"[{ticker}] Fetching news (last {days} days)")
    try:
        data = _fetch(ticker, days=days)
        NEWS_DIR.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return data
    except Exception as e:
        logger.error(f"[{ticker}] News fetch failed: {e}")
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                pass
        return {"ticker": ticker, "articles": [], "sentiment": {}, "fetched_at": None}


def fetch_and_save(ticker: str, days: int = 14) -> dict:
    """Force-refresh news and save to disk."""
    data = _fetch(ticker, days=days)
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(ticker)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"[{ticker}] News saved → {path}")
    return data
