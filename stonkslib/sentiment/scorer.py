"""Batch LLM sentiment scorer.

For each ticker-day that has stored news but no sentiment row yet, aggregate that
day's headlines + summaries and ask the local LLM (same OpenAI-compatible endpoint
the optimizer uses, `llm/client.py`) for a 1-10 score, a stock-relevant summary,
and one line of reasoning. Results are upserted into `news_sentiment`.

This is a *batch* step: scores are precomputed and read at backtest/alert time, so
the live signal path never calls an LLM and backtests stay deterministic.
Idempotent — already-scored ticker-days are skipped, so re-runs are cheap.
"""

import json

from stonkslib.llm import client
from stonkslib.utils import news_store

# Keep prompts bounded — most signal is in the headline; cap count + summary length.
_MAX_ARTICLES = 25
_MAX_SUMMARY_CHARS = 400

_SYSTEM = (
    "You are a financial news analyst. You are given the news articles published "
    "about a single stock on a single day. Judge how the day's news affects that "
    "stock's outlook and return STRICT JSON only, with keys:\n"
    '  "score": integer 1-10 (1=very bearish, 5=neutral/no real news, 10=very bullish),\n'
    '  "summary": one or two sentences capturing ONLY the stock-relevant information '
    "(earnings, guidance, analyst rating changes, products, legal/regulatory, M&A, "
    "macro that hits this name). Ignore clickbait, ads, and generic market recaps.\n"
    '  "reasoning": one short sentence tying the summary to the score.\n'
    "Output the JSON object and nothing else."
)


def _build_prompt(ticker: str, date: str, articles: list[dict]) -> str:
    lines = [f"Stock: {ticker}", f"Date: {date}", "", "Articles:"]
    for a in articles[:_MAX_ARTICLES]:
        headline = (a.get("headline") or "").strip()
        summary = (a.get("summary") or "").strip()[:_MAX_SUMMARY_CHARS]
        source = (a.get("source") or "").strip()
        line = f"- [{source}] {headline}"
        if summary and summary != headline:
            line += f" — {summary}"
        lines.append(line)
    return "\n".join(lines)


def _parse(content: str) -> dict | None:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    if "score" not in data:
        return None
    try:
        score = float(data["score"])
    except (TypeError, ValueError):
        return None
    score = max(1.0, min(10.0, score))  # clamp to the 1-10 scale
    return {
        "score": score,
        "summary": str(data.get("summary", "")).strip(),
        "reasoning": str(data.get("reasoning", "")).strip(),
    }


def score_ticker(ticker: str, model: str | None = None, verbose: bool = True) -> int:
    """Score every unscored day for one ticker. Returns the number newly scored."""
    ticker = ticker.upper()
    model = model or client.default_model()
    dates = news_store.unscored_dates(ticker)
    if not dates:
        if verbose:
            print(f"  [=] {ticker}: nothing new to score")
        return 0

    scored = 0
    for date in dates:
        articles = news_store.articles_on(ticker, date)
        if not articles:
            continue
        prompt = _build_prompt(ticker, date, articles)
        try:
            content = client.chat(
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                model=model,
                json_mode=True,
                timeout=120,
            )
        except Exception as e:
            print(f"  [!] {ticker} {date}: LLM error: {e} "
                  f"(LLM reachable at {client.base_url()}?)")
            continue
        parsed = _parse(content)
        if parsed is None:
            print(f"  [!] {ticker} {date}: unparseable LLM output, skipped")
            continue
        news_store.save_sentiment(
            ticker, date, parsed["score"], parsed["summary"],
            parsed["reasoning"], len(articles), model,
        )
        scored += 1
        if verbose:
            print(f"  [✓] {ticker} {date}: {parsed['score']:.0f}/10 "
                  f"({len(articles)} articles)")
    return scored


def score_pending(tickers: list[str], model: str | None = None,
                  verbose: bool = True) -> int:
    """Score all unscored ticker-days across the given tickers. Returns total scored."""
    total = 0
    for ticker in tickers:
        total += score_ticker(ticker, model=model, verbose=verbose)
    return total
