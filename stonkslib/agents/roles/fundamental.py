"""Fundamental Analyst — reads valuation, quality, and the long-term picture."""

from stonkslib.agents.base import Agent, register

_KEEP = ("ticker", "interval", "price", "fundamentals", "dividends",
         "earnings", "sentiment", "news", "freshness")


class FundamentalAnalyst(Agent):
    def facts_for(self, snapshot: dict, context: dict) -> dict:
        return {k: snapshot[k] for k in _KEEP if k in snapshot}


register(FundamentalAnalyst(
    name="fundamental_analyst",
    title="Fundamental Analyst",
    stage="analyst",
    role_prompt=(
        "ROLE: Fundamental Analyst. Assess valuation (P/E trailing vs forward, "
        "market cap, analyst target vs price), business quality (profit margin, "
        "revenue growth), dividend profile (for income/DCA suitability), and "
        "earnings proximity (a near date raises event risk). Be skeptical of rich "
        "valuations and reward durable quality. Note when fundamentals data is "
        "missing or stale."
    ),
    schema={
        "thesis": "2-3 sentence read on the business and valuation, from the facts only",
        "valuation_read": "cheap | fair | rich, with the metric that drives it",
        "quality_flags": ["short notes on margins, growth, dividend, earnings risk"],
        "lean": "bullish | neutral | bearish",
        "confidence": "high | medium | low",
    },
))
