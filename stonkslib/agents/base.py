"""Agent framework — scalable roster of hedge-fund role-agents.

Every agent is the *same* local model (Hermes via `LLM_MODEL`) wearing a
different role: a system prompt, an expected JSON output shape, and a function
that turns the shared `TickerSnapshot` (+ upstream agents' output) into its slice
of the prompt. Adding a role later = one subclass + one `register()` call; the
orchestrator and dashboard pick it up automatically.

Pipeline stages run in order (`STAGES`); within a stage agents are independent.
Each agent's parsed output is accumulated into a `context` dict keyed by agent
name, which downstream stages receive — so researchers see the analysts, and the
portfolio manager sees everyone.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from stonkslib.llm import client

logger = logging.getLogger(__name__)

# Ordered pipeline stages. Agents declare which stage they belong to.
STAGES = ["analyst", "research", "manager"]

# Shared discipline prepended to every role's system prompt. The model runs
# locally with a frozen training cutoff, so it must never narrate stale events as
# current — the single most important constraint in the whole design.
COMMON_RULES = (
    "You are one role on a hedge-fund team reasoning over a structured FACTS "
    "block about a single ticker. Follow these hard rules:\n"
    "1. Reason ONLY from the FACTS provided. Do NOT use any knowledge of current "
    "events from your own memory — your training is stale and will be wrong about "
    "anything time-sensitive.\n"
    "2. The supplied news headlines are your ONLY source of current-event "
    "context. If none are present, say 'no current news available' and do not "
    "speculate about lawsuits, executives, products, or macro events.\n"
    "3. Do not predict prices. State what the data shows and give your role's "
    "read on it.\n"
    "4. Return VALID JSON ONLY — a single object, no prose outside it."
)


@dataclass
class Agent:
    """One role on the team. Subclass or instantiate, then `register()`.

    name    machine slug, unique (e.g. "fundamental_analyst")
    title   display name (e.g. "Fundamental Analyst")
    stage   one of STAGES — controls pipeline ordering
    role_prompt   role-specific system prompt (COMMON_RULES is prepended)
    schema  the JSON object the role must return (shown verbatim in the prompt)
    """

    name: str
    title: str
    stage: str
    role_prompt: str
    schema: dict = field(default_factory=dict)

    # ── overridable hooks ──────────────────────────────────────────────────────
    def facts_for(self, snapshot: dict, context: dict) -> dict:
        """The slice of the snapshot this role should see. Default: the whole
        snapshot. Override to trim noise (e.g. a fundamental analyst can drop the
        intraday confluence readouts)."""
        return snapshot

    def system_prompt(self) -> str:
        return f"{COMMON_RULES}\n\n{self.role_prompt}"

    def user_prompt(self, snapshot: dict, context: dict) -> str:
        facts = self.facts_for(snapshot, context)
        upstream = {k: v for k, v in context.items()} if context else {}
        parts = [
            f"FACTS for {snapshot.get('ticker')} ({snapshot.get('interval')}):",
            json.dumps(facts, indent=2, default=str),
        ]
        if upstream:
            parts += [
                "\nYour teammates have already weighed in. Their findings:",
                json.dumps(upstream, indent=2, default=str),
            ]
        parts += [
            "\nReturn ONLY this JSON object:",
            json.dumps(self.schema, indent=2),
        ]
        return "\n".join(parts)

    def fallback(self) -> dict:
        """Returned when the LLM call or JSON parse fails."""
        return {"error": "agent unavailable", "_agent": self.name}

    def postprocess(self, out: dict, snapshot: dict, context: dict) -> dict:
        """Normalize/validate the parsed output. Default: passthrough."""
        return out

    # ── run ────────────────────────────────────────────────────────────────────
    def run(self, snapshot: dict, context: dict | None = None,
            model: str | None = None) -> dict:
        context = context or {}
        try:
            content = client.chat(
                messages=[
                    {"role": "system", "content": self.system_prompt()},
                    {"role": "user", "content": self.user_prompt(snapshot, context)},
                ],
                model=model,
                json_mode=True,
            )
            out = json.loads(content)
            return self.postprocess(out, snapshot, context)
        except Exception as e:
            logger.warning("[agent:%s] failed for %s: %s",
                           self.name, snapshot.get("ticker"), e)
            return self.fallback()


# ── registry ────────────────────────────────────────────────────────────────────

_ROSTER: dict[str, Agent] = {}


def register(agent: Agent) -> Agent:
    """Add an agent to the global roster (idempotent by name)."""
    if agent.stage not in STAGES:
        raise ValueError(f"agent {agent.name!r} has unknown stage {agent.stage!r}")
    _ROSTER[agent.name] = agent
    return agent


def roster() -> list[Agent]:
    """All registered agents, ordered by pipeline stage then registration order."""
    return sorted(_ROSTER.values(), key=lambda a: STAGES.index(a.stage))


def agents_in_stage(stage: str) -> list[Agent]:
    return [a for a in _ROSTER.values() if a.stage == stage]


def get(name: str) -> Agent | None:
    return _ROSTER.get(name)
