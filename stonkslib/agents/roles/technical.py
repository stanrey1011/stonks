"""Technical Analyst — reads the confluence votes and whether backtests validate them."""

from stonkslib.agents.base import Agent, register

_KEEP = ("ticker", "interval", "price", "confluence", "edge", "leap_edge",
         "earnings", "short_interest", "freshness")


class TechnicalAnalyst(Agent):
    def facts_for(self, snapshot: dict, context: dict) -> dict:
        return {k: snapshot[k] for k in _KEEP if k in snapshot}


register(TechnicalAnalyst(
    name="technical_analyst",
    title="Technical Analyst",
    stage="analyst",
    role_prompt=(
        "ROLE: Technical Analyst. Read the confluence block (per-indicator BUY/"
        "SELL votes and weighted buy/sell scores) and the backtest edge. CRITICAL: "
        "the confluence is the current setup; the 'edge'/'leap_edge' blocks say "
        "whether that *kind* of setup has actually worked on this ticker "
        "historically (win_rate, trades, net_pnl / avg_pnl_pct). A strong "
        "confluence with no validated edge is a weak signal — say so. Distinguish "
        "swing edge (shares) from leap edge (options)."
    ),
    schema={
        "trend_read": "what the votes and scores currently say",
        "edge_note": "does the backtest validate this setup? cite win_rate/trades; "
                     "note swing vs leap separately if they differ",
        "signal_summary": "1-2 sentences combining setup + validation",
        "lean": "bullish | neutral | bearish",
        "confidence": "high | medium | low",
    },
))
