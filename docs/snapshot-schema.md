# TickerSnapshot schema — the data contract

`stonkslib/snapshot.py::hydrate(ticker, interval="1d", news_days=7)` returns one
`TickerSnapshot` dict — the single source of truth for "what do we know about
this ticker right now?". Every consumer (dashboard pages, the multi-agent fund,
the CLI) reads this instead of touching the ~7 data directories directly.

**Implement agents against this schema, not against the underlying files.** If a
field is missing here, add it in `hydrate()` once — never re-discover the file
layout in a consumer.

```python
from stonkslib.snapshot import hydrate, hydrate_watchlist

snap = hydrate("NVDA")                 # one ticker
snaps = hydrate_watchlist()            # whole watchlist (stocks + etfs)
```

In the multi-agent fund, agents receive this as `report["snapshot"]` (see
`stonkslib/agents/orchestrator.py`).

---

## Guarantees

- **Never raises.** Each section is wrapped in its own try/except. A dead source
  becomes `{"error": "<reason>"}` in that section only — the rest still populates.
  Always check `if "error" in snap["<section>"]` before reading a section's fields.
- **Stable keys.** Top-level keys are always present (possibly as an `error`
  dict). Inner fields may be `None` when the source has no value.
- **Freshness, not just values.** `snap["freshness"]` tells you whether each
  source is stale, so the caller can decide whether to trust it.

---

## Top-level shape

```python
{
  "ticker": "NVDA",
  "interval": "1d",
  "snapshot_at": "2026-06-22T20:30:00+00:00",   # ISO, when hydrate() ran

  "price":          {...},   # from cleaned Parquet via load_td()
  "confluence":     {...},   # LIVE strategy engine (same path as the backtester)
  "edge":           {...},   # cached SWING backtest metrics
  "leap_edge":      {...},   # cached LEAP backtest metrics
  "fundamentals":   {...},   # yfinance, 24h cache
  "dividends":      {...},   # yfinance
  "earnings":       {...},   # yfinance + Finnhub, 24h cache
  "sentiment":      {...},   # local-LLM scores (sqlite) + Finnhub strip
  "news":           {...},   # Finnhub headlines + sentiment, 4h cache
  "short_interest": {...},   # yfinance, 72h cache
  "freshness":      {...},   # per-source {updated_at, stale}
}
```

---

## Sections

### `price`  — source: `load_td()` (cleaned Parquet)
```python
{
  "close": 135.42,
  "prev_close": 133.80,
  "day_change_pct": 1.21,     # vs prev_close, or None
  "high_52w": 152.89,         # trailing 252 bars (High col, falls back to Close)
  "low_52w": 78.34,
  "volume": 48200000.0,       # latest bar, or None
}
```
> Note: `load_td` **title-cases** columns (`Close`, `High`, `Volume`). The
> snapshot reads them case-insensitively; do the same if you bypass it.

### `confluence`  — source: live engine (`build_namespace`/`vote_signals`/`confluence_scores`)
```python
{
  "buy_score": 0.72,          # weighted, latest bar
  "sell_score": 0.15,
  "votes": [
    {"indicator": "rsi", "vote": "BUY"},      # vote ∈ {"BUY","SELL","—"}
    {"indicator": "macd", "vote": "—"},
    # rsi, macd, bollinger, supertrend, markov, news_sentiment
  ],
  "readouts": {"close": 135.42, "rsi": 38.2, "macd": 0.84, "macd_signal": 0.6,
               "st_dir": 1, "mk_bull": 0.55, "mk_bear": 0.20, "news_sent": 7},
  "asof": "2026-06-22 00:00:00",
  "degraded": [],             # indicators dropped due to infra failure
}
```
> **Graceful degradation:** if an optional indicator that needs external infra
> fails (e.g. `news_sentiment` can't reach the sentiment DB), the engine reruns
> with the core set (rsi/macd/bollinger/supertrend/markov) and lists the dropped
> ones in `degraded`. So `votes` may have fewer than 6 entries — check
> `degraded` if an agent wants to weight a missing signal.

### `edge`  — source: `data/backtest_results/strategy/{ticker}/{interval}/*_metrics.json`
Validated **swing** (share) edge. Empty until `stonks backtest`/`optimize` runs.
```python
{
  "strategies": [
    {"strategy": "rsi_macd", "win_rate": 0.61, "net_pnl": 4280.0,
     "max_drawdown": 0.123, "trades": 34},
  ],
  "has_edge": True,           # any strategy clears the floors (below)
  "best": {...},              # highest win_rate among qualifying, or None
}
```
**Edge floors** (configurable at top of `snapshot.py`):
`win_rate >= 0.50` **and** `trades >= 5` **and** `net_pnl > 0`.

### `leap_edge`  — source: `data/backtest_results/leaps/{ticker}/{interval}/*_metrics.json`
Validated **LEAP** (options) edge. Scored by `avg_pnl_pct`, not net P&L (per the
LEAP backtest design). Empty until LEAP backtests run.
```python
{
  "strategies": [
    {"strategy": "supertrend", "option_type": "call", "win_rate": 0.58,
     "avg_pnl_pct": 24.0, "net_pnl": 1200.0, "trades": 12},
  ],
  "has_edge": True,           # floors: win_rate>=0.50, trades>=5, avg_pnl_pct>0
  "best": {...},              # highest avg_pnl_pct among qualifying, or None
}
```

### `fundamentals`  — source: `get_fundamentals()`
```python
{
  "name": "NVIDIA Corporation", "sector": "Technology", "industry": "Semiconductors",
  "market_cap": 3.34e12, "trailing_pe": 55.2, "forward_pe": 28.4, "eps_ttm": 2.4,
  "beta": 1.7, "week52_high": 152.9, "week52_low": 78.3,
  "profit_margin": 0.55, "revenue_growth": 0.78,    # fractions (0-1)
  "target_mean": 160.0, "recommendation": "buy",
}
```

### `dividends`  — source: `get_dividends()`  (matters for the DCA bucket)
```python
{"dividend_yield": 0.0003, "dividend_rate": 0.04, "payout_ratio": 0.02,
 "ex_date": "2026-06-05"}   # yield/rate fractions; None when no dividend
```

### `earnings`  — source: `get_earnings()`
```python
{
  "next_date": "2026-08-20",          # ISO date or None
  "next_eps_estimate": 0.82,
  "last_surprise_pct": 8.3,           # derived from history (most recent quarter)
  "last_reported_date": "2026-05-21",
}
```

### `sentiment`  — source: `load_sentiment_rows()` (local-LLM sqlite) + Finnhub strip
```python
{
  "llm": [{"date": "2026-06-21", "score": 7.4, "summary": "...",
           "reasoning": "...", "n_articles": 12}, ...],   # newest first, up to 14
  "latest": 7.4,                       # most recent LLM score (1-10), or None
  "finnhub": {"bullish_pct": 68.0, "bearish_pct": 12.0, "buzz": 1.4,
              "articles_week": 40, "weekly_average": 28, "company_score": 0.8},
}
```

### `news`  — source: `get_news()`  (Finnhub, 4h cache)
```python
{
  "articles": [   # up to 8, newest first
    {"datetime": 1718632800, "date": "2026-06-17", "headline": "...",
     "source": "Reuters", "summary": "...", "url": "https://...", "category": "..."},
  ],
  "finnhub": {...},   # same sentiment strip as sentiment.finnhub
}
```
> **Agent discipline:** `news.articles` is the ONLY current-event context. If it
> is empty, agents must say "no current news available" and not speculate — the
> local model's training is stale (enforced by `COMMON_RULES` in `agents/base.py`).

### `short_interest`  — source: `get_short_interest()`
```python
{"short_pct": 0.012,        # fraction of float (0-1), or None
 "days_to_cover": 1.8, "shares_short": 45000000.0, "mom_change": -5.2}
```

### `freshness`  — computed from file mtimes vs per-source TTL
```python
{
  "price":          {"updated_at": "2026-06-22T20:00:00+00:00", "stale": False},
  "backtest":       {"updated_at": None, "stale": True},
  "fundamentals":   {...}, "earnings": {...}, "news": {...}, "short_interest": {...},
}
```
TTLs (hours): price 24, fundamentals 48, earnings 48, news 8, short_interest 96,
backtest 168. `updated_at: None` ⇒ source has never been written ⇒ `stale: True`.

---

## Verifying availability on the deployment

This schema is the *contract*; whether real values flow depends on data being
present and API keys being set. On the host where the data lives:

```sh
venv/bin/python -m stonkslib.snapshot NVDA      # prints the full snapshot JSON
```

Skim for any section reading `"error"`. Expected non-fatal gaps:
- `edge` / `leap_edge` empty until `stonks backtest` / `stonks optimize` have run.
- `news` / `earnings` / `short_interest` / Finnhub `sentiment` need `FINNHUB_API_KEY`.
- `sentiment.llm` empty until news sentiment has been scored (News page seed).

---

## Extending the snapshot

Add a field in **one** place — `hydrate()` in `snapshot.py`:

1. Guard the new source in its own `try/except` block.
2. Add a `freshness[...]` entry if it has a cache file.
3. Document the new field here.
4. If an agent needs it, widen that role's `_KEEP` tuple in
   `stonkslib/agents/roles/<role>.py` (agents trim the snapshot per role).

Do **not** gather data inside an agent or a dashboard page.
