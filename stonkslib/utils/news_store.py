"""Historical news store + LLM sentiment scores (SQLite).

stonks keeps OHLCV in Parquet and short-lived API responses in flat JSON caches
(`utils/news.py`, `utils/earnings.py`). The *historical* news archive and the
per-day LLM sentiment scores need keyed upserts and "what's not scored yet"
queries, so they live in a small SQLite db here — stdlib only, no new dependency.

Two tables:
  news_articles(ticker, id, ...)        — every Finnhub company-news article kept forever
  news_sentiment(ticker, date, score..) — one LLM-scored row per ticker-day (1-10)

This module is intentionally pandas-free so the backfill/scoring CLIs run without
the analysis stack; the indicator (`indicators/news_sentiment.py`) builds the
aligned Series from the plain rows returned here.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path

from stonkslib.utils.news import _finnhub_get  # reuse the rate-limited Finnhub client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "db" / "news.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS news_articles (
    ticker   TEXT    NOT NULL,
    id       INTEGER NOT NULL,
    datetime INTEGER,
    date     TEXT,
    headline TEXT,
    source   TEXT,
    summary  TEXT,
    url      TEXT,
    category TEXT,
    PRIMARY KEY (ticker, id)
);
CREATE INDEX IF NOT EXISTS idx_articles_ticker_date ON news_articles (ticker, date);

CREATE TABLE IF NOT EXISTS news_sentiment (
    ticker     TEXT NOT NULL,
    date       TEXT NOT NULL,
    score      REAL,
    summary    TEXT,
    reasoning  TEXT,
    n_articles INTEGER,
    model      TEXT,
    scored_at  TEXT,
    PRIMARY KEY (ticker, date)
);
"""


@contextmanager
def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        con.executescript(_SCHEMA)
        yield con
        con.commit()
    finally:
        con.close()


def _normalize(item: dict) -> dict | None:
    """Map a raw Finnhub company-news item to our article row (None if no id)."""
    aid = item.get("id")
    if aid is None:
        return None
    ts = item.get("datetime", 0)
    date = (
        datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        if ts else None
    )
    return {
        "id":       int(aid),
        "datetime": ts,
        "date":     date,
        "headline": item.get("headline", ""),
        "source":   item.get("source", ""),
        "summary":  item.get("summary", ""),
        "url":      item.get("url", ""),
        "category": item.get("category", ""),
    }


def _upsert_articles(con, ticker: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    con.executemany(
        """
        INSERT INTO news_articles
            (ticker, id, datetime, date, headline, source, summary, url, category)
        VALUES (:ticker, :id, :datetime, :date, :headline, :source, :summary, :url, :category)
        ON CONFLICT(ticker, id) DO UPDATE SET
            headline=excluded.headline, summary=excluded.summary,
            source=excluded.source, url=excluded.url, category=excluded.category
        """,
        [{**r, "ticker": ticker} for r in rows],
    )
    return len(rows)


def backfill(ticker: str, days: int = 365, window_days: int = 30) -> int:
    """Fetch ticker company-news back `days` (Finnhub free tier ≈ 1y) into SQLite.

    Walks the range in `window_days` chunks (smaller payloads, plays nice with the
    1.1s rate limit in `news._finnhub_get`). Idempotent — re-runs upsert by article id.
    Returns the number of articles fetched.
    """
    ticker = ticker.upper()
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    total = 0
    with _connect() as con:
        cursor = start
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=window_days - 1), end)
            try:
                raw = _finnhub_get("/company-news", {
                    "symbol": ticker,
                    "from": cursor.strftime("%Y-%m-%d"),
                    "to": chunk_end.strftime("%Y-%m-%d"),
                })
            except Exception as e:
                print(f"  [!] {ticker} {cursor}..{chunk_end}: {e}")
                cursor = chunk_end + timedelta(days=1)
                continue
            rows = [n for n in (_normalize(i) for i in (raw or [])) if n]
            total += _upsert_articles(con, ticker, rows)
            cursor = chunk_end + timedelta(days=1)
    return total


def unscored_dates(ticker: str) -> list[str]:
    """Dates (YYYY-MM-DD) that have articles but no sentiment row yet, ascending."""
    ticker = ticker.upper()
    with _connect() as con:
        rows = con.execute(
            """
            SELECT DISTINCT a.date
            FROM news_articles a
            LEFT JOIN news_sentiment s ON s.ticker = a.ticker AND s.date = a.date
            WHERE a.ticker = ? AND a.date IS NOT NULL AND s.date IS NULL
            ORDER BY a.date
            """,
            [ticker],
        ).fetchall()
    return [r[0] for r in rows]


def articles_on(ticker: str, date: str) -> list[dict]:
    """All stored articles for a ticker on a given YYYY-MM-DD, newest first."""
    ticker = ticker.upper()
    with _connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT headline, source, summary, url FROM news_articles "
            "WHERE ticker = ? AND date = ? ORDER BY datetime DESC",
            [ticker, date],
        ).fetchall()
    return [dict(r) for r in rows]


def save_sentiment(ticker: str, date: str, score: float, summary: str,
                   reasoning: str, n_articles: int, model: str) -> None:
    """Upsert one LLM-scored ticker-day."""
    with _connect() as con:
        con.execute(
            """
            INSERT INTO news_sentiment
                (ticker, date, score, summary, reasoning, n_articles, model, scored_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, date) DO UPDATE SET
                score=excluded.score, summary=excluded.summary,
                reasoning=excluded.reasoning, n_articles=excluded.n_articles,
                model=excluded.model, scored_at=excluded.scored_at
            """,
            [ticker.upper(), date, score, summary, reasoning, n_articles, model,
             datetime.now(timezone.utc).isoformat()],
        )


def load_score_rows(ticker: str) -> list[tuple[str, float]]:
    """(date, score) pairs for a ticker, ascending — the indicator builds its Series
    from these (keeps this module pandas-free)."""
    ticker = ticker.upper()
    with _connect() as con:
        rows = con.execute(
            "SELECT date, score FROM news_sentiment "
            "WHERE ticker = ? AND score IS NOT NULL ORDER BY date",
            [ticker],
        ).fetchall()
    return [(r[0], float(r[1])) for r in rows]


def load_sentiment_rows(ticker: str, limit: int = 60) -> list[dict]:
    """Recent scored ticker-days (newest first) for display on the News page."""
    ticker = ticker.upper()
    with _connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT date, score, summary, reasoning, n_articles, model FROM news_sentiment "
            "WHERE ticker = ? ORDER BY date DESC LIMIT ?",
            [ticker, limit],
        ).fetchall()
    return [dict(r) for r in rows]
