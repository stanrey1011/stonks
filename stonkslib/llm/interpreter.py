"""
LLM-based signal interpretation.

Takes rule-based signals + recent indicator readings and asks an LLM
to assess conviction level and provide plain-English reasoning.
"""
import json
import logging
import pandas as pd

from stonkslib.llm import client

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen2.5:7b"

_SYSTEM = (
    "You are a technical analysis assistant. "
    "Analyze trading setups and return structured conviction assessments. "
    "Return valid JSON only — no text outside the JSON object."
)

_PROMPT = """Ticker: {ticker} | Interval: {interval} | Weekly trend: {weekly_trend}

Rule-based signals fired:
{signal_summary}

Recent indicator readings (newest last):
{indicator_table}

Assess this setup:
- Do the indicators genuinely support the signal direction?
- Are there any conflicting signals or warning signs?
- What is your conviction level?

Return ONLY this JSON:
{{
  "direction": "bullish" or "bearish" or "neutral",
  "conviction": "high" or "medium" or "low" or "none",
  "reasoning": "1-2 sentences max — be specific about what the data shows"
}}"""


def _build_table(indicator_data: dict, n: int = 10) -> str:
    """Format last N bars of indicator readings as a readable table."""
    if not indicator_data:
        return "(no indicator data)"

    dates  = indicator_data.get("dates", [])[-n:]
    closes = indicator_data.get("close", [])[-n:]
    rows   = [f"{'Date':<12} {'Close':>8}"]

    optional = [
        ("RSI",   indicator_data.get("rsi",    []), "{:>6.1f}"),
        ("MACD",  indicator_data.get("macd",   []), "{:>+7.3f}"),
        ("BB%",   indicator_data.get("bb_pct", []), "{:>+6.1f}%"),
        ("MA",    indicator_data.get("ma_pos", []), "{:>14}"),
        ("ST",    indicator_data.get("st_dir", []), "{:>10}"),
    ]

    # build header
    header = f"{'Date':<12} {'Close':>8}"
    for col_name, series, _ in optional:
        if series:
            header += f"  {col_name:>8}"
    rows = [header, "-" * len(header)]

    for i, (d, c) in enumerate(zip(dates, closes)):
        line = f"{str(d)[:10]:<12} {c:>8.2f}"
        for _, series, fmt in optional:
            if series:
                idx = len(series) - len(dates) + i
                try:
                    val = series[idx]
                    line += "  " + fmt.format(val)
                except (IndexError, TypeError, ValueError):
                    line += "  " + " " * 8
        rows.append(line)

    return "\n".join(rows)


def interpret_signal(
    ticker: str,
    interval: str,
    signals: list[dict],
    indicator_data: dict,
    weekly_trend: str = "unknown",
    model: str = DEFAULT_MODEL,
) -> dict:
    """
    Ask the LLM to interpret a set of rule-based signals.

    Returns a dict with keys: direction, conviction, reasoning.
    Falls back to {"direction": "unknown", "conviction": "none", "reasoning": "LLM unavailable"}
    on any error.
    """
    fallback = {"direction": "unknown", "conviction": "none", "reasoning": "LLM unavailable"}

    if not signals:
        return fallback

    signal_summary = "\n".join(
        f"  [{s['type']}] {s['reason']}" for s in signals
    )
    indicator_table = _build_table(indicator_data)
    prompt = _PROMPT.format(
        ticker=ticker,
        interval=interval,
        weekly_trend=weekly_trend,
        signal_summary=signal_summary,
        indicator_table=indicator_table,
    )

    try:
        content = client.chat(
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            model=model,
            json_mode=True,
        )
        result = json.loads(content)
        return {
            "direction":  result.get("direction",  "unknown"),
            "conviction": result.get("conviction", "none"),
            "reasoning":  result.get("reasoning",  ""),
        }
    except Exception as e:
        logger.error(f"[interpreter] LLM error: {e} (LLM reachable at {client.base_url()}?)")
        return fallback
