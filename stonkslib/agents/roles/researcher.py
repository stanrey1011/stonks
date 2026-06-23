"""Researchers — a bull and a bear who argue the case after seeing the analysts.

Two agents in the same `research` stage. Each receives the snapshot plus the
analysts' output (via context) and makes the strongest honest case for its side.
This is the TradingAgents-style bull/bear debate, kept to one round for now.
"""

from stonkslib.agents.base import Agent, register

_KEEP = ("ticker", "interval", "price", "confluence", "edge", "leap_edge",
         "fundamentals", "earnings", "sentiment", "news")


class Researcher(Agent):
    def facts_for(self, snapshot: dict, context: dict) -> dict:
        return {k: snapshot[k] for k in _KEEP if k in snapshot}


register(Researcher(
    name="bull_researcher",
    title="Bull Researcher",
    stage="research",
    role_prompt=(
        "ROLE: Bull Researcher. Make the strongest HONEST case to BUY, grounded "
        "only in the facts and the analysts' findings. Lead with validated edge and "
        "confluence, support with valuation/quality and any positive news. You must "
        "still acknowledge the single biggest risk — a bull who ignores risk is "
        "useless to the team."
    ),
    schema={
        "argument": "the strongest case to buy, 2-4 sentences",
        "key_supports": ["the specific facts that back the bull case"],
        "biggest_risk_acknowledged": "the one thing that could break this thesis",
    },
))


register(Researcher(
    name="bear_researcher",
    title="Bear Researcher",
    stage="research",
    role_prompt=(
        "ROLE: Bear Researcher. Make the strongest HONEST case to AVOID or stay "
        "out, grounded only in the facts and the analysts' findings. Lead with "
        "absent/weak edge, rich valuation, bearish confluence, earnings risk, or "
        "negative news. State plainly what evidence would change your mind."
    ),
    schema={
        "argument": "the strongest case to avoid/skip, 2-4 sentences",
        "key_concerns": ["the specific facts that back the bear case"],
        "what_would_change_my_mind": "the evidence that would flip you constructive",
    },
))
