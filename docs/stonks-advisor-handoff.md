# Stonks Advisor — handoff

This document is a complete implementation handoff for the **Advisor** feature in the stonks app. It was designed in a multi-turn conversation covering data architecture, LLM integration, and UI layout. The person implementing this has full context of the stonks codebase (see `CLAUDE.md`). Everything described here builds on existing `stonkslib` modules — no new dependencies, no database migrations.

---

## Problem statement

The stonks app has grown feature-by-feature over time. The data it computes is solid — confluence signals, backtested strategies, fundamentals, sentiment, earnings, news, short interest — but it's scattered across 7 directories, 3 file formats, and 4 different cache TTLs. Each feature learned independently where to find each piece. There is no single function that answers "what do I know about NVDA right now?" without touching 7 different paths.

The Advisor feature needs a unified data layer underneath it. So this handoff covers two things: (1) the data unification layer (`snapshot.py`), and (2) the advisor itself (facts + LLM reasoning + Streamlit dashboard).

---

## Part 1: Data unification — `stonkslib/snapshot.py`

### What it does

One module, one function: `hydrate(ticker, interval="1d")` → returns a single `TickerSnapshot` dict containing everything the app knows about a ticker, with freshness timestamps on every piece. Every consumer — dashboard pages, advisor, agents, CLI — imports `hydrate()` instead of independently querying 7 directories.

### Why it matters

- `analyst_brief()` in `stonkslib/agents/analyst.py` is already 80% of this, but it's buried in `agents/`, missing backtest edge + short interest + freshness tracking, and has 5 independent try/except blocks stapling sources together
- Signal drift risk: `check_signals()` recomputes live while pre-saved CSVs in `data/analysis/signals/` can disagree silently
- New features must independently learn where to find each piece — the ADHD build pattern where each feature re-discovers the file layout
- No way to answer "what's stale?" without checking mtimes across multiple directories

### The `TickerSnapshot` schema

```python
{
    "ticker": "NVDA",
    "interval": "1d",
    "snapshot_at": "2026-06-19T20:30:00+00:00",  # when hydrate() ran

    # --- Price ---
    "price": {
        "close": 135.42,
        "prev_close": 133.80,
        "day_change_pct": 1.21,
        "high_52w": 152.89,
        "low_52w": 78.34,
        "volume": 48200000,
    },

    # --- Confluence (live engine, not pre-saved CSVs) ---
    "confluence": {
        "buy_score": 0.72,
        "sell_score": 0.15,
        "votes": [
            {"indicator": "rsi", "vote": "BUY"},
            {"indicator": "macd", "vote": "BUY"},
            {"indicator": "bollinger", "vote": "—"},
            {"indicator": "supertrend", "vote": "BUY"},
            {"indicator": "markov", "vote": "—"},
            {"indicator": "news_sentiment", "vote": "BUY"},
        ],
        "readouts": {"close": 135.42, "rsi": 38.2, "macd": 0.84, "st_dir": 1, "mk_bull": 0.55},
    },

    # --- Validated edge (from cached backtest metrics) ---
    "edge": {
        "has_edge": True,
        "strategies": [
            {"strategy": "rsi_macd", "win_rate": 0.61, "net_pnl": 4280.0, "max_drawdown": 0.123, "trades": 34},
            {"strategy": "supertrend", "win_rate": 0.53, "net_pnl": 1100.0, "max_drawdown": 0.18, "trades": 22},
        ],
        "best": {"strategy": "rsi_macd", "win_rate": 0.61, "net_pnl": 4280.0, "max_drawdown": 0.123, "trades": 34},
    },

    # --- Fundamentals ---
    "fundamentals": {
        "name": "NVIDIA Corporation",
        "sector": "Technology",
        "industry": "Semiconductors",
        "market_cap": 3340000000000,
        "trailing_pe": 55.2,
        "forward_pe": 28.4,
        "profit_margin": 0.55,
        "revenue_growth": 0.78,
    },

    # --- Earnings ---
    "earnings": {
        "next_date": "2026-08-20",
        "next_eps_estimate": 0.82,
        "last_surprise_pct": 8.3,
    },

    # --- Sentiment ---
    "sentiment": {
        "llm_score": 0.74,           # latest from news_store
        "finnhub_bullish_pct": 68.0,
        "finnhub_bearish_pct": 12.0,
        "finnhub_buzz_ratio": 1.4,
    },

    # --- News (recent headlines for LLM context) ---
    "news": [
        {
            "headline": "NVIDIA announces next-gen Rubin architecture",
            "summary": "...",
            "source": "Reuters",
            "datetime": "2026-06-17T14:30:00",
        },
        # ... up to 8 headlines
    ],

    # --- Short interest ---
    "short_interest": {
        "short_pct_float": 1.2,
        "days_to_cover": 1.8,
        "shares_short": 45000000,
        "mom_change_pct": -5.2,
    },

    # --- Freshness (per-source, computed from file mtimes / cache metadata) ---
    "freshness": {
        "price": {"updated_at": "2026-06-19T20:00:00", "stale": False},
        "fundamentals": {"updated_at": "2026-06-19T08:00:00", "stale": False},
        "earnings": {"updated_at": "2026-06-19T08:00:00", "stale": False},
        "news": {"updated_at": "2026-06-19T16:30:00", "stale": False},
        "short_interest": {"updated_at": "2026-06-17T12:00:00", "stale": False},
        "backtest": {"updated_at": "2026-06-15T10:00:00", "stale": True},  # older than 7d
    },
}
```

### Implementation notes

- Create `stonkslib/snapshot.py` with `hydrate(ticker, interval="1d") -> dict`
- Each section is independently guarded (try/except per source, same pattern as `analyst_brief`) — one failure never blanks the rest
- **Confluence must come from the live engine** (`build_namespace` / `vote_signals` / `confluence_scores` via the existing `_ta_summary` logic in `agents/analyst.py`), NOT from pre-saved signal CSVs. This pins the signal source of truth to the same path the backtester uses.
- **Edge** reads cached `*_metrics.json` files from `data/backtest_results/strategy/{ticker}/{interval}/` via glob. A strategy "has edge" if: `win_rate >= 0.50`, `trades >= 5`, `net_pnl > 0`. These floors are configurable constants at the top of the module.
- **Freshness** checks file mtimes against each source's expected TTL. Mark stale if: price data older than 1 day (weekday), fundamentals/earnings older than 48h, news older than 8h, short interest older than 96h, backtest older than 7d. Return the `updated_at` timestamp and a boolean `stale` flag per source.
- **Price** section is derived from the cleaned Parquet via `load_td()`. Compute `day_change_pct` from the last two closes, `high_52w`/`low_52w` from the trailing 252 bars.

### Source function mapping

| Snapshot field | Existing source function | Module |
|---|---|---|
| `price` | `load_td([ticker], interval)` | `stonkslib/utils/load_td.py` |
| `confluence` | `build_namespace()` / `vote_signals()` / `confluence_scores()` | `stonkslib/strategies/engine.py` |
| `edge` | `glob(BACKTEST_BASE / ticker / interval / "*_metrics.json")` | `stonkslib/backtest/strategy.py` paths |
| `fundamentals` | `get_fundamentals(ticker)` | `stonkslib/utils/fundamentals.py` |
| `earnings` | `get_earnings(ticker)` | `stonkslib/utils/earnings.py` |
| `sentiment` (LLM) | `load_sentiment_rows(ticker)` | `stonkslib/utils/news_store.py` |
| `sentiment` (Finnhub) | `get_news(ticker)` → `.sentiment` | `stonkslib/utils/news.py` |
| `news` | `get_news(ticker)` → `.articles` | `stonkslib/utils/news.py` |
| `short_interest` | `get_short_interest(ticker)` | `stonkslib/utils/short_interest.py` |

### Refactoring `analyst_brief`

After `snapshot.py` exists, refactor `stonkslib/agents/analyst.py::analyst_brief()` to call `hydrate()` and reshape its return dict from the snapshot. This makes `analyst_brief` a thin view over the canonical snapshot instead of an independent gather. The Analyst dashboard page (`14_Analyst.py`) continues to call `analyst_brief()` unchanged.

### Watchlist helper

Add `hydrate_watchlist(interval="1d", categories=("stocks", "etfs")) -> list[dict]` that reads `tickers.yaml`, calls `hydrate()` per ticker, and returns the list. This replaces the ad-hoc watchlist loops scattered across `owui_tool.py`, `cli/alert.py`, and the advisor.

---

## Part 2: Advisor module — `stonkslib/advisor/`

### Architecture — two stages, one ranks, the other annotates

**Stage 1 — Facts (deterministic, no LLM).** For each ticker on the watchlist, call `hydrate()` to get the full snapshot. Rank the watchlist by a deterministic key:

```
rank_key = (
    1 if has_edge else 0,       # validated strategies first
    confluence.buy_score,        # higher confluence = higher rank
    -(forward_pe or 9999),       # lower valuation as tiebreaker
)
```

The ranking is set entirely by the computed facts. The LLM never reorders it.

**Stage 2 — Reasoning (LLM, advisory only).** For each ticker, hand the snapshot to the local LLM via `stonkslib/llm/client.chat(json_mode=True)` and get back:

```python
{
    "facts_summary": "2-3 sentence plain restatement of what the numbers show",
    "context_read": "what the headlines/sentiment imply, or 'no current news available'",
    "lean": "buy" | "wait" | "skip",
    "rationale": "1-2 sentences — the LLM's two cents",
    "suggested_entry": "price level or condition, or null"
}
```

The LLM's lean rides alongside the facts as annotation. It never changes the ranking.

### Critical LLM prompt discipline

The system prompt must enforce these rules because the model runs locally (Qwen3/DeepSeek on anton) with a frozen training cutoff:

1. **Reason ONLY from the supplied snapshot.** Do not use any knowledge of current events from your own memory — your training is stale.
2. **The `news` list is the ONLY source of current-event context.** If it is empty, set `context_read` to "no current news available" and do not speculate about ongoing situations.
3. **If `edge.has_edge` is false**, the lean should not be "buy" on technicals alone.
4. Return valid JSON only.

This is the single most important design constraint. Without it, the local model will confidently narrate stale events as if they're current — the exact failure mode that makes the "two cents" dangerous instead of useful.

### Files to create

**`stonkslib/advisor/__init__.py`**

```python
"""Two-stage watchlist advisor — facts (stonks) + reasoning (LLM)."""
from stonkslib.advisor.core import gather, reason, advise_watchlist, render

__all__ = ["gather", "reason", "advise_watchlist", "render"]
```

**`stonkslib/advisor/core.py`**

Functions:

- `gather(ticker, interval="1d") -> dict` — calls `hydrate()` from `snapshot.py` (or directly assembles the facts bundle if snapshot.py isn't built yet — see the reference implementation below). Returns the facts dict that feeds the LLM prompt.
- `reason(facts, model=None) -> dict` — Stage 2. Sends the facts to the LLM, parses the JSON response, normalizes the lean to `buy`/`wait`/`skip`. Falls back gracefully on LLM error.
- `advise_watchlist(interval="1d", categories=("stocks", "etfs"), model=None, tickers=None) -> list[dict]` — loops the watchlist, calls `gather` + `reason` per ticker, sorts by the deterministic rank key. Returns a list of `{"ticker": str, "facts": dict, "advice": dict}`.
- `render(cards) -> str` — terminal-friendly rendering of the ranked cards.

### Reference implementation for `core.py`

This was drafted during the design conversation and works against the existing codebase without `snapshot.py` as a prerequisite. It calls `analyst_brief()` directly and layers in the backtest edge. Once `snapshot.py` exists, `gather()` should be refactored to call `hydrate()` instead.

```python
"""Two-stage watchlist advisor: stonks computes the facts, the LLM reasons over them.

Stage 1 (deterministic — gather): for one ticker, assemble everything the app
already computes — confluence votes + scores from the live strategy engine
(via analyst_brief), the validated edge from cached backtest metrics, plus
fundamentals / earnings proximity / sentiment / recent headlines.

Stage 2 (LLM — reason): hand that bundle to the local model and get back a
plain restatement of the facts, a contextual read of the news/sentiment, and a
lean (buy / wait / skip) with a one-liner rationale and an optional entry.

advise_watchlist loops the watchlist, ranks by the facts (NOT by the LLM's
opinion), and attaches each name's lean as advisory annotation. You pull the
trigger.
"""

from __future__ import annotations

import glob
import json
import logging
from pathlib import Path

import yaml

from stonkslib.agents.analyst import analyst_brief
from stonkslib.llm import client

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
BACKTEST_BASE = PROJECT_ROOT / "data" / "backtest_results" / "strategy"

MIN_WIN_RATE = 0.50
MIN_TRADES = 5


# ── Stage 1 — facts ──────────────────────────────────────────────────────────

def _load_backtest_edge(ticker: str, interval: str) -> dict:
    """Read cached *_metrics.json for this ticker/interval and summarize edge."""
    out = {"strategies": [], "has_edge": False, "best": None}
    pattern = str(BACKTEST_BASE / ticker / interval / "*_metrics.json")
    for path in sorted(glob.glob(pattern)):
        try:
            with open(path) as f:
                m = json.load(f)
        except Exception:
            continue
        entry = {
            "strategy": m.get("strategy", Path(path).stem.replace("_metrics", "")),
            "win_rate": m.get("win_rate"),
            "net_pnl": m.get("net_pnl"),
            "max_drawdown": m.get("max_drawdown"),
            "trades": m.get("trades"),
        }
        out["strategies"].append(entry)

    qualifying = [
        s for s in out["strategies"]
        if (s["win_rate"] or 0) >= MIN_WIN_RATE
        and (s["trades"] or 0) >= MIN_TRADES
        and (s["net_pnl"] or 0) > 0
    ]
    if qualifying:
        out["has_edge"] = True
        out["best"] = max(qualifying, key=lambda s: s["win_rate"] or 0)
    return out


def gather(ticker: str, interval: str = "1d", news_days: int = 7) -> dict:
    """Assemble the deterministic facts bundle for one ticker."""
    ticker = ticker.upper()
    brief = analyst_brief(ticker, interval=interval, news_days=news_days)

    ta = brief.get("ta") or {}
    buy_score = ta.get("buy_score") or 0.0
    sell_score = ta.get("sell_score") or 0.0
    votes = ta.get("votes") or []

    edge = _load_backtest_edge(ticker, interval)

    fund = brief.get("fundamentals") or {}
    earn = brief.get("earnings") or {}
    news = brief.get("news") or {}
    sent = brief.get("sentiment") or {}

    return {
        "ticker": ticker,
        "interval": interval,
        "asof": ta.get("asof"),
        "confluence": {
            "buy_score": round(buy_score, 3),
            "sell_score": round(sell_score, 3),
            "votes": votes,
        },
        "backtest": edge,
        "fundamentals": {
            "name": fund.get("name"),
            "sector": fund.get("sector"),
            "trailing_pe": fund.get("trailing_pe"),
            "forward_pe": fund.get("forward_pe"),
            "market_cap": fund.get("market_cap"),
        },
        "earnings": {
            "next_date": earn.get("next_date"),
            "next_eps_estimate": earn.get("next_eps_estimate"),
        },
        "sentiment_latest": sent.get("latest"),
        "news": {
            "finnhub": news.get("finnhub") or {},
            "headlines": [
                {"headline": a.get("headline"), "summary": a.get("summary"),
                 "source": a.get("source"), "datetime": a.get("datetime")}
                for a in (news.get("articles") or [])[:8]
            ],
        },
    }


# ── Stage 2 — reasoning ──────────────────────────────────────────────────────

_SYSTEM = (
    "You are an investing assistant that reasons over a structured FACTS block "
    "about a single ticker. You do NOT predict prices and you do NOT decide for "
    "the user — you restate what the data shows and offer a lean with your "
    "reasoning, like a colleague's two cents.\n\n"
    "HARD RULES:\n"
    "1. Reason ONLY from the FACTS block provided. Do not use any knowledge of "
    "current events from your own memory — your training is stale and you will be "
    "wrong about anything time-sensitive.\n"
    "2. The 'news.headlines' list is your ONLY source of current-event context. "
    "If it is empty, set context_read to 'no current news available' and do not "
    "speculate about ongoing situations, lawsuits, executives, or macro events.\n"
    "3. If the backtest shows no edge (has_edge=false), your lean should not be "
    "'buy' on technicals alone — say so.\n"
    "4. Return VALID JSON ONLY, no text outside the object."
)

_PROMPT = """FACTS for {ticker} ({interval}), as of {asof}:

{facts_json}

Return ONLY this JSON object:
{{
  "facts_summary": "2-3 sentence plain-English restatement of what the numbers show (confluence + whether the backtest validates edge + earnings proximity)",
  "context_read": "what the supplied headlines/sentiment imply, or 'no current news available' if headlines is empty",
  "lean": "buy" | "wait" | "skip",
  "rationale": "1-2 sentences — your two cents, weighing the facts against the context",
  "suggested_entry": "a price level or condition to wait for, or null"
}}"""


_FALLBACK = {
    "facts_summary": "",
    "context_read": "LLM unavailable",
    "lean": "wait",
    "rationale": "Reasoning step failed; review the facts manually.",
    "suggested_entry": None,
}


def reason(facts: dict, model: str | None = None) -> dict:
    """Stage 2: hand the facts bundle to the local model, get back its lean."""
    prompt = _PROMPT.format(
        ticker=facts.get("ticker"),
        interval=facts.get("interval"),
        asof=facts.get("asof"),
        facts_json=json.dumps(facts, indent=2, default=str),
    )
    try:
        content = client.chat(
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt},
            ],
            model=model,
            json_mode=True,
        )
        out = json.loads(content)
        lean = str(out.get("lean", "wait")).lower().strip()
        out["lean"] = lean if lean in ("buy", "wait", "skip") else "wait"
        return out
    except Exception as e:
        logger.warning("[advisor] reasoning failed for %s: %s", facts.get("ticker"), e)
        return dict(_FALLBACK)


# ── Orchestration ─────────────────────────────────────────────────────────────

def _watchlist(categories: tuple[str, ...] = ("stocks", "etfs")) -> list[str]:
    """Flat list of tickers from tickers.yaml. Crypto excluded by default."""
    try:
        with open(TICKER_YAML) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return []
    out: list[str] = []
    for cat in categories:
        out.extend(data.get(cat) or [])
    return out


def _facts_rank_key(facts: dict) -> tuple:
    """Deterministic ranking — the LLM's lean never reorders."""
    bt = facts.get("backtest") or {}
    conf = facts.get("confluence") or {}
    fund = facts.get("fundamentals") or {}
    fwd_pe = fund.get("forward_pe")
    return (
        1 if bt.get("has_edge") else 0,
        conf.get("buy_score") or 0.0,
        -(fwd_pe if isinstance(fwd_pe, (int, float)) else 9_999),
    )


def advise_watchlist(
    interval: str = "1d",
    categories: tuple[str, ...] = ("stocks", "etfs"),
    model: str | None = None,
    tickers: list[str] | None = None,
) -> list[dict]:
    """Run the full two-stage pass over the watchlist."""
    names = tickers or _watchlist(categories)
    cards = []
    for t in names:
        try:
            facts = gather(t, interval=interval)
        except Exception as e:
            logger.warning("[advisor] gather failed for %s: %s", t, e)
            continue
        advice = reason(facts, model=model)
        cards.append({"ticker": facts["ticker"], "facts": facts, "advice": advice})

    cards.sort(key=lambda c: _facts_rank_key(c["facts"]), reverse=True)
    return cards


def render(cards: list[dict]) -> str:
    """Terminal-friendly rendering of the ranked cards."""
    lines = []
    for c in cards:
        f, a = c["facts"], c["advice"]
        conf = f["confluence"]
        bt = f["backtest"]
        edge = bt.get("best")
        edge_str = (
            f"edge: {edge['strategy']} {edge['win_rate']:.0%} win, "
            f"${edge['net_pnl']:.0f} P&L, {edge['max_drawdown']:.0%} maxDD"
            if edge else "edge: none validated"
        )
        nd = f["earnings"].get("next_date")
        lean = a["lean"].upper()
        lines.append(f"━━ {c['ticker']}  [{lean}]")
        lines.append(f"   facts:  BUY {conf['buy_score']:.2f} / SELL {conf['sell_score']:.2f} · {edge_str}"
                     + (f" · earnings {nd}" if nd else ""))
        lines.append(f"   read:   {a['context_read']}")
        lines.append(f"   2¢:     {a['rationale']}"
                     + (f"  (entry: {a['suggested_entry']})" if a.get("suggested_entry") else ""))
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    interval = sys.argv[1] if len(sys.argv) > 1 else "1d"
    cards = advise_watchlist(interval=interval)
    print(render(cards))
```

### CLI integration

Add a `stonks advise` subcommand in `stonkslib/cli/main.py`:

```python
@cli.command()
@click.argument("target", default="all")
@click.option("--interval", default="1d")
@click.option("--model", default=None, help="LLM model override")
def advise(target, interval, model):
    """Run the two-stage advisor over the watchlist."""
    from stonkslib.advisor.core import advise_watchlist, render
    tickers = None if target == "all" else [target.upper()]
    cards = advise_watchlist(interval=interval, tickers=tickers, model=model)
    click.echo(render(cards))
```

---

## Part 3: Advisor dashboard page — `stonkslib/dash/pages/15_Advisor.py`

### Layout — three-panel split

The dashboard page has three visual zones:

```
┌─────────────────────────────────────────────────┐
│  Ticker selector row (clickable pills)          │
├───────────────────────┬─────────────────────────┤
│                       │                         │
│       FACTS           │      REASONING          │
│   (left panel)        │    (right panel)        │
│                       │                         │
│  Confluence scores    │  "What the numbers say" │
│  Indicator votes      │  "What the headlines    │
│  Validated edge       │   say"                  │
│  Fundamentals         │  Recent headlines list  │
│  Earnings proximity   │  ──────────────         │
│  Sentiment scores     │  Two cents (italic)     │
│                       │  Suggested entry        │
│                       │                         │
├───────────────────────┴─────────────────────────┤
│                                                 │
│  WATCHLIST SUMMARY — ranked cards               │
│                                                 │
│  ┌─────────────────────────────────────────┐    │
│  │ NVDA [BUY]                              │    │
│  │ Edge: rsi_macd 61% · BUY 0.72 · ...    │    │
│  │ "Setup is clean across all inputs..."   │    │
│  └─────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────┐    │
│  │ AMD [WAIT]  ⚠ Earnings in 6 wks        │    │
│  │ Edge: supertrend 54% · BUY 0.48 · ...  │    │
│  │ "Confluence is middling..."             │    │
│  └─────────────────────────────────────────┘    │
│  ... more cards ...                             │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Left panel — facts (no LLM, purely computed)

This panel displays the raw output from `gather()` / `hydrate()`. It should feel like a data sheet, not a narrative.

**Confluence section:**
- BUY score and SELL score as large numbers (green for BUY > 0.5, red for SELL > 0.5)
- Indicator votes as colored pills: green "RSI buy", red "MACD sell", gray "Bollinger —"
- Use the same color scheme as the existing Confluence page (`2_Confluence.py`)

**Validated edge section:**
- "Validated edge: ✓ Yes" or "✗ None" with color
- Best strategy name, win rate, net P&L, max drawdown
- Number of trades in the sample

**Fundamentals section:**
- Forward P/E, trailing P/E, market cap, sector
- Keep it compact — one row per metric

**Earnings section:**
- Next earnings date
- Days until earnings (computed, with warning color if < 14 days)
- Next EPS estimate

**Sentiment section:**
- LLM sentiment score (from news_store)
- Finnhub bullish %, bearish %, buzz ratio

### Right panel — reasoning (LLM output)

This panel displays the output from `reason()`. It should feel like a colleague's notes.

**"What the numbers say"** — the `facts_summary` field. 2-3 sentences restating the confluence, edge, and earnings proximity in plain English.

**"What the headlines say"** — the `context_read` field. What the sentiment and news imply, or "no current news available" if the feed is empty.

**Recent headlines** — a compact list of the top headlines from `news.headlines`, each showing the headline text, source, and relative time ("2d ago"). Clickable to open the article URL if available.

**Divider**

**"Two cents"** — the `rationale` field, displayed in italic. This is the LLM's lean.

**Suggested entry** — the `suggested_entry` field, if not null. Displayed as a subtle callout.

### Bottom section — watchlist summary cards

One card per watchlist ticker, ranked by `_facts_rank_key` (validated edge first, then confluence, then valuation). Each card shows:

- Ticker name + lean badge (BUY = green, WAIT = amber, SKIP = gray)
- One-line facts: edge summary, BUY score, forward P/E, earnings date, sentiment score
- Warning flag if earnings are within 14 days (amber pill with ⚠ icon)
- The `rationale` in italic below the facts line

### Streamlit implementation notes

- The ticker selector at the top uses `st.pills()` or a row of `st.button()` calls. Clicking a ticker updates `st.session_state["advisor_ticker"]` and the split panels re-render for that ticker.
- The two-column split uses `st.columns([1, 1])` for the facts/reasoning panels.
- The bottom cards use a loop with `st.container()` per card, styled with custom CSS or `st.markdown()` with HTML.
- **Cache the advisor results** with `@st.cache_data(ttl=1800)` on the `advise_watchlist` call. The LLM reasoning is expensive; don't re-run it on every widget interaction.
- The page should have a "Refresh" button that clears the cache and re-runs the full advisor pass.
- Add the page to `stonkslib/dash/app.py` in the navigation dict under the appropriate section (probably "Analysis" alongside Confluence, Signals, etc.). Use `title="Advisor"`.
- Follow existing dashboard patterns: page-prefixed `key=` on all widgets (e.g., `key="advisor_ticker"`), `@st.cache_data` on data-loading functions, session state for persisting selections across navigation.

### Freshness indicators

If `snapshot.py` is implemented with the `freshness` field, show small colored dots next to each section header in the facts panel:
- Green dot = data is fresh (within expected TTL)
- Amber dot = data is aging (within 2x TTL)
- Red dot = data is stale (beyond 2x TTL)

This answers "can I trust these numbers?" at a glance.

---

## Implementation order

The recommended build sequence, where each step is independently useful:

1. **`stonkslib/advisor/core.py` + `__init__.py`** — the reference implementation above works against the existing codebase with no prerequisites. Test with `python -m stonkslib.advisor.core 1d` to see the terminal output. This validates that the two-stage flow works end to end.

2. **`stonks advise` CLI command** — wire the advisor into the Click group. Now you can run `stonks advise` or `stonks advise NVDA` from the terminal.

3. **`stonkslib/snapshot.py`** — the data unification layer. Once this exists, refactor `gather()` in `core.py` to call `hydrate()` instead of `analyst_brief()` + `_load_backtest_edge()`. Also refactor `analyst_brief()` to be a thin view over `hydrate()`.

4. **`stonkslib/dash/pages/15_Advisor.py`** — the Streamlit dashboard page with the three-panel layout. This is the UI payoff — the visual tool you'll actually use when you have cash to deploy.

5. **Open WebUI integration** — add an `advise` method to the `Tools` class in `owui_tool.py` so the LLM chat interface can run the advisor. Simple wrapper: call `advise_watchlist()`, return `render(cards)`.

Steps 1 and 2 can ship today. Step 3 is the foundation work. Step 4 is the polish. Step 5 is optional convenience.

---

## What this is NOT

- **Not a portfolio optimizer.** There is no position sizing, mean-variance optimization, VaR, or correlation matrix. You decide how much to put in each name. The tool ranks and annotates; you allocate.
- **Not a prediction engine.** The LLM does not predict prices. It restates facts and gives a lean based on the supplied context. The "accuracy" comes from the backtest validation — did the signal pattern actually work on this ticker historically? — not from the LLM's opinion.
- **Not a trading bot.** Nothing auto-executes. The advisor outputs a ranked list with reasoning. You review it, you decide, you place the trade yourself.
- **Not a LEAP scanner replacement.** LEAPs are excluded from this flow by design. The existing `stonks leaps` command and scanner handle that use case. The advisor covers the share-buying decision.

---

## Future — LangGraph upgrade (Phase 2, not now)

Once the single-threaded advisor is working and the leans feel useful, the LangGraph upgrade is mechanical:

- The `gather()` calls across the watchlist become parallel fan-outs via LangGraph's `Send` / map pattern
- `gather` and `reason` become two graph nodes with a shared `TypedDict` state
- A supervisor node merges and ranks the results
- A DuckDB ledger (via `import/to_duckdb.py`) tracks recommendations and forward outcomes for calibration scoring

Don't build this until the sequential version proves the leans are worth reading. The parallelism is a performance optimization, not a capability unlock.

---

## Future — web search for broader context (Phase 3, not now)

The current-event coverage is bounded by Finnhub `/company-news`, which catches ticker-specific items well but misses broader themes ("Altman's in a legal fight, so cool on the whole AI sector"). Adding a web-search tool to the reasoning step would fill this gap, but `llm/client.py` is a plain OpenAI-compatible client with no tools wired in — this is a real addition, not a flag flip.

Ship on Finnhub headlines first. See if the gap actually bites in practice. Add search only if it does.
