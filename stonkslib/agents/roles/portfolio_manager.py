"""Portfolio Manager — synthesizes the team and issues a per-vehicle verdict.

The PM sees the full snapshot plus every upstream agent (analysts + bull/bear).
It returns one verdict per trading vehicle — LEAP, DCA, Swing — because the same
facts imply different actions per vehicle: a name with no swing edge but a cheap
valuation and a dividend can still be a DCA "accumulate".

`postprocess` normalizes each vehicle's lean to a known token so the dashboard
and CLI can color-code without guessing.
"""

from stonkslib.agents.base import Agent, register

_LEANS = {
    "leap": {"buy_call", "buy_put", "wait", "skip"},
    "dca": {"accumulate", "hold", "avoid"},
    "swing": {"buy", "wait", "sell", "skip"},
}
_DEFAULT = {"leap": "skip", "dca": "avoid", "swing": "wait"}


class PortfolioManager(Agent):
    def postprocess(self, out: dict, snapshot: dict, context: dict) -> dict:
        verdicts = out.get("verdicts") or {}
        for vehicle, allowed in _LEANS.items():
            v = verdicts.get(vehicle) or {}
            lean = str(v.get("lean", "")).lower().strip().replace(" ", "_")
            v["lean"] = lean if lean in allowed else _DEFAULT[vehicle]
            verdicts[vehicle] = v
        out["verdicts"] = verdicts
        conv = str(out.get("conviction", "")).lower().strip()
        out["conviction"] = conv if conv in {"high", "medium", "low"} else "low"
        return out

    def fallback(self) -> dict:
        return {
            "summary": "Portfolio manager unavailable; review the analyst and "
                       "researcher output manually.",
            "verdicts": {
                "leap": {"lean": "skip", "rationale": "no synthesis"},
                "dca": {"lean": "avoid", "rationale": "no synthesis"},
                "swing": {"lean": "wait", "rationale": "no synthesis"},
            },
            "conviction": "low",
            "_agent": self.name,
        }


register(PortfolioManager(
    name="portfolio_manager",
    title="Portfolio Manager",
    stage="manager",
    role_prompt=(
        "ROLE: Portfolio Manager. Weigh the analysts and the bull/bear debate "
        "against the facts and issue a decision for EACH vehicle:\n"
        "- LEAP (long-dated options): lean on the leap_edge block; buy_call needs "
        "bullish confluence + validated leap edge, buy_put the inverse; else wait/skip.\n"
        "- DCA (dollar-cost accumulation of shares over time): favor durable "
        "quality, reasonable valuation, and dividends; tolerant of weak short-term "
        "technicals; accumulate / hold / avoid.\n"
        "- SWING (shares over weeks): lean on confluence + the swing 'edge' block; "
        "buy needs setup + validated edge, else wait/sell/skip.\n"
        "Be decisive but honest. If edge is unvalidated, do not 'buy' on technicals "
        "alone. Flag near-term earnings as event risk."
    ),
    schema={
        "summary": "2-3 sentence synthesis of the team's view",
        "verdicts": {
            "leap": {"lean": "buy_call | buy_put | wait | skip",
                     "rationale": "1 sentence", "suggested": "strike/expiry hint or null"},
            "dca": {"lean": "accumulate | hold | avoid", "rationale": "1 sentence"},
            "swing": {"lean": "buy | wait | sell | skip",
                      "rationale": "1 sentence", "suggested_entry": "price/condition or null"},
        },
        "conviction": "high | medium | low",
    },
))
