"""Orchestrator — runs the agent roster over a snapshot, stage by stage.

`run_fund(ticker)` hydrates the snapshot once, then walks the pipeline stages in
order. Within a stage every agent runs against the same upstream context; each
agent's output is added to the context the next stage sees. The result is a
`FundReport`: the facts plus every agent's reasoning, with the portfolio
manager's per-vehicle verdict surfaced at the top.

The deterministic facts (snapshot) are the source of truth; the agents annotate
them. Ranking a watchlist is done on the facts, never on the LLM's opinion.
"""

from __future__ import annotations

import logging

from stonkslib.agents.base import STAGES, agents_in_stage, roster  # noqa: F401
from stonkslib.snapshot import hydrate
import stonkslib.agents.roles  # noqa: F401  (import = register the roster)

logger = logging.getLogger(__name__)


def run_fund(ticker: str, interval: str = "1d", model: str | None = None,
             snapshot: dict | None = None) -> dict:
    """Run the full agent chain for one ticker. Returns a FundReport dict."""
    snap = snapshot or hydrate(ticker, interval=interval)

    context: dict = {}
    agents_run: list[dict] = []
    for stage in STAGES:
        stage_agents = agents_in_stage(stage)
        stage_out: dict = {}
        for agent in stage_agents:
            out = agent.run(snap, context=context, model=model)
            stage_out[agent.name] = out
            agents_run.append({"name": agent.name, "title": agent.title,
                               "stage": stage, "output": out})
        # Make this stage's output visible to the next stage.
        context.update(stage_out)

    pm = context.get("portfolio_manager") or {}
    return {
        "ticker": snap.get("ticker"),
        "interval": interval,
        "snapshot": snap,
        "agents": agents_run,           # ordered analyst -> research -> manager
        "verdict": pm,                  # portfolio manager's per-vehicle call
    }


def _facts_rank_key(snap: dict) -> tuple:
    """Deterministic ranking — the LLM never reorders. Validated edge first, then
    confluence buy score, then cheaper valuation as a tiebreaker."""
    edge = snap.get("edge") or {}
    leap = snap.get("leap_edge") or {}
    conf = snap.get("confluence") or {}
    fund = snap.get("fundamentals") or {}
    fwd_pe = fund.get("forward_pe")
    return (
        1 if (edge.get("has_edge") or leap.get("has_edge")) else 0,
        conf.get("buy_score") or 0.0,
        -(fwd_pe if isinstance(fwd_pe, (int, float)) else 9_999),
    )


def run_fund_watchlist(interval: str = "1d",
                       categories: tuple[str, ...] = ("stocks", "etfs"),
                       model: str | None = None,
                       tickers: list[str] | None = None) -> list[dict]:
    """Run the chain across the watchlist, ranked by the facts (not the LLM)."""
    from stonkslib.snapshot import _watchlist
    names = tickers or _watchlist(categories)
    reports = []
    for t in names:
        try:
            reports.append(run_fund(t, interval=interval, model=model))
        except Exception as e:
            logger.warning("[orchestrator] run_fund failed for %s: %s", t, e)
    reports.sort(key=lambda r: _facts_rank_key(r["snapshot"]), reverse=True)
    return reports


def render(reports: list[dict]) -> str:
    """Terminal-friendly rendering of the ranked fund reports."""
    lines = []
    for r in reports:
        v = (r.get("verdict") or {}).get("verdicts") or {}
        leap = v.get("leap") or {}
        dca = v.get("dca") or {}
        swing = v.get("swing") or {}
        conv = (r.get("verdict") or {}).get("conviction", "?")
        lines.append(f"━━ {r['ticker']}  (conviction: {conv})")
        lines.append(f"   LEAP : {str(leap.get('lean','?')).upper():10} {leap.get('rationale','')}")
        lines.append(f"   DCA  : {str(dca.get('lean','?')).upper():10} {dca.get('rationale','')}")
        lines.append(f"   SWING: {str(swing.get('lean','?')).upper():10} {swing.get('rationale','')}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    tkr = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    print(render([run_fund(tkr)]))
