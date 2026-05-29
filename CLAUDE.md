# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```sh
python3.13 -m venv venv   # Python 3.13 required — 3.14 breaks numpy
source venv/bin/activate
pip install -r requirements.txt
```

The `stonks` CLI is installed as a package entry point. All commands require the venv to be active.

## Common Commands

```sh
stonks pipeline                          # fetch → clean → analyze all tickers (1d)
stonks pipeline AAPL --interval 1wk      # single ticker
stonks alert all --all-strategies        # scan latest bar, post to Discord
stonks backtest AAPL --strategy rsi.yaml
stonks optimize --all-strategies --all-tickers --iterations 5
stonks optimize --all-strategies --per-ticker --all-tickers   # per-ticker YAMLs
stonks status                            # data freshness + what's optimized
stonks earnings-refresh                  # refresh earnings cache for all tickers
stonks earnings-refresh NVDA             # single ticker
stonks earnings-refresh stocks           # by category

# LEAP commands
stonks leaps stocks                      # scan watchlist for LEAP opportunities
stonks leaps-backtest NVDA --option-type call --interval 1wk
stonks leaps-backtest NVDA --option-type auto   # auto-picks call/put per signal
stonks optimize --all-strategies --per-ticker --leaps --option-type call --all-tickers
stonks leaps-trades NVDA                 # show entry/exit dates for chart verification
stonks leaps-trades NVDA --option-type put --strategy supertrend
```

Positional target accepts a ticker (`AAPL`), a category (`stocks`/`etfs`/`crypto`), or `all`. Fetching a ticker directly (without `stonks tickers add`) doesn't modify `tickers.yaml`.

## Automation

All scheduled tasks run via **systemd user timers** — no cron jobs. Check status with:
```sh
systemctl --user list-timers --all | grep stonks
journalctl --user -u stonks-pipeline -f    # follow logs for any service
```

### Systemd services summary

| Timer | Schedule | Script | Does |
|---|---|---|---|
| `stonks-pipeline.timer` | Mon–Fri 20:00 UTC | `scripts/nightly_pipeline.sh` | fetch → clean → analyze all tickers (1d + 1wk) |
| `stonks-alert.timer` | Mon–Fri 20:30 UTC | `scripts/daily_alert.sh` | signal scan + LEAP scan → Discord |
| `stonks-optimize.timer` | Mon–Fri 10:00 UTC | `scripts/nightly_optimize.sh` | two-phase LLM strategy optimization |
| `stonks-earnings.timer` | Sat–Sun 12:00 UTC | `scripts/refresh_earnings.sh` | earnings cache refresh (Finnhub + yfinance) |

```sh
# Control
systemctl --user restart stonks-bot                  # after code changes
systemctl --user start stonks-pipeline.service       # trigger pipeline now
systemctl --user start stonks-alert.service          # trigger alert scan now
systemctl --user start stonks-earnings.service       # trigger earnings refresh now

# Enable/disable a timer
systemctl --user enable --now stonks-earnings.timer
systemctl --user disable stonks-earnings.timer
```

### Pipeline (scripts/nightly_pipeline.sh + stonks-pipeline.timer)
Runs Mon–Fri at 20:00 UTC (4pm ET, right at market close). Fetches fresh OHLCV data, cleans, and runs signal analysis for all tickers at 1d and 1wk intervals. The alert timer fires 30 minutes later at 20:30 UTC, so data is always fresh when alerts run.

### Alert scan (scripts/daily_alert.sh + stonks-alert.timer)
Runs Mon–Fri at 20:30 UTC. Runs `stonks alert` (1d + 1wk) and `stonks leaps` and posts results to Discord webhook.

### Nightly optimization (scripts/nightly_optimize.sh + stonks-optimize.timer)
Runs Mon–Fri at 10:00 UTC (midnight HST). Two-phase approach:
1. **Phase 1** — `qwen2.5:7b`, 3 iterations for 1d and 1wk: broad parameter exploration, saves optimized YAMLs
2. **Phase 2** — `qwen2.5:32b`, 3 iterations with `--warm-start`: loads Phase 1 YAMLs as starting point, refines with the larger model

`--warm-start` checks for an existing `optimized/{name}_{ticker}_optimized.yaml` and starts from it instead of the base strategy. Use `--leaps` + `--per-ticker` to save LEAP-specific per-ticker YAMLs.

### Weekend earnings refresh (scripts/refresh_earnings.sh + stonks-earnings.timer)
Runs Sat–Sun at 12:00 UTC. Calls `stonks earnings-refresh` which loops all non-crypto watchlist tickers and force-refreshes the Finnhub + yfinance earnings cache. Keeps next-earnings dates and EPS estimates current so the Watchlist countdown and Chart overlays are accurate on Monday morning. Also runs automatically as part of `stonks pipeline` (1d interval only) on weekdays.

## Architecture

### Data flow

```
fetch (yfinance → raw CSV)
  → clean (normalize OHLCV → Parquet)
    → analyze (indicators + patterns → signal CSVs)
      → merge (combine signals into unified CSVs)
        → backtest / alert
```

`stonks pipeline` runs fetch → clean → analyze → merge in one shot. `stonks alert` reads the already-cleaned Parquet and computes signals on the fly from the strategy YAML.

### Storage layout

| Path | Contents |
|---|---|
| `data/ticker_data/raw/{ticker}/` | Raw CSV files per interval |
| `data/ticker_data/clean/{ticker}/{interval}.parquet` | Cleaned OHLCV (all analysis reads from here) |
| `data/analysis/signals/{ticker}/{interval}/` | Per-indicator and per-pattern CSV outputs |
| `data/analysis/merged/by-indicators/{ticker}/` | All indicator signals merged |
| `data/analysis/merged/by-patterns/{ticker}/` | All pattern signals merged |
| `data/backtest_results/strategy/{ticker}/{interval}/` | Regular backtest JSON + CSV |
| `data/backtest_results/leaps/{ticker}/{interval}/` | LEAP backtest CSV + metrics JSON |
| `data/ticker_data/earnings/{ticker}.json` | Earnings cache: history + next date (24h TTL) |
| `data/ticker_data/news/{ticker}.json` | News cache: articles + sentiment (4h TTL) |
| `data/last_alert.json` | Last Alerts scan result — persists signal badges on Watchlist across browser refreshes |

All data directories are gitignored.

### Key modules

- **`stonkslib/cli/main.py`** — Click group wiring all subcommands
- **`stonkslib/fetch/td.py`** — `fetch_all()`: yfinance download, freshness guard via `fetch/guard.py`
- **`stonkslib/clean/td.py`** — `clean_td()`: normalizes raw CSVs to Parquet
- **`stonkslib/analysis/signals.py`** — `aggregate_and_save()`: runs every indicator and pattern detector, writes CSVs to `data/analysis/signals/`
- **`stonkslib/merge/by_indicators.py`** / **`by_patterns.py`** — joins the per-indicator CSVs into a single merged view
- **`stonkslib/backtest/strategy.py`** — `run_strategy_backtest()`: fills at next-bar open with slippage, returns metrics dict
- **`stonkslib/backtest/leaps.py`** — `run_leaps_backtest()`: Black-Scholes LEAP simulation; exits on stop-loss (50% premium) or expiry only — no signal exits (user decides)
- **`stonkslib/alerts/signals.py`** — `check_signals()`: same indicator logic as backtest but only checks the latest bar (uses last 100 bars for indicator warmup)
- **`stonkslib/leaps/scanner.py`** — `scan_leaps()`: aggregates BUY/SELL counts, fetches VIX rank + live options chain, ranks LEAP candidates
- **`stonkslib/llm/optimizer.py`** — `optimize()`: iteratively runs backtests, sends results to Ollama, applies JSON suggestions, saves best params; supports `use_leaps=True` for LEAP-aware prompts scoring avg trade % instead of net P&L
- **`stonkslib/utils/load_td.py`** — `load_td()`: canonical way to load cleaned Parquet into a dict of DataFrames
- **`stonkslib/cli/earnings_refresh.py`** — `stonks earnings-refresh` command: loops watchlist tickers, calls `fetch_and_save`, skips crypto (tickers ending in `-USD`). Used by `scripts/refresh_earnings.sh` and runnable ad-hoc.
- **`stonkslib/utils/earnings.py`** — hybrid earnings fetcher: yfinance for deep history (limit=40, exact announcement dates + EPS/surprise), Finnhub `/stock/earnings` for the most recent 4 quarters that yfinance lags, Finnhub `/calendar/earnings` for exact upcoming date. Results cached to `data/ticker_data/earnings/{ticker}.json` with 24h TTL. Rate-limited to 1.1s between Finnhub calls (free tier: 60/min). Called by pipeline on `interval == "1d"`.
- **`stonkslib/utils/news.py`** — Finnhub news fetcher: `/company-news` for articles (headline, summary, source, url) and `/news-sentiment` for bullish%/bearish%/buzz ratio. Results cached to `data/ticker_data/news/{ticker}.json` with 4h TTL. Rate-limited to 1.1s. Used by owui_tool `get_ticker_summary` + `get_news`, and the News dashboard page.
- **`stonkslib/owui_tool.py`** — Open WebUI Tools class v1.4.0 (install via Workspace → Tools); exposes all CLI features including LEAP tools and news to the LLM chat interface

### Strategy YAML fallback chain

All commands (alert, backtest, LEAP backtest, signal scan) resolve strategy YAMLs in this priority order:

1. `optimized/{name}_{ticker}_leaps_{option_type}_optimized.yaml` — LEAP-specific per-ticker
2. `optimized/{name}_{ticker}_optimized.yaml` — per-ticker (regular)
3. `optimized/{name}_optimized.yaml` — global optimized
4. `{name}.yaml` — base strategy

### Strategies

YAML files in `stonkslib/strategies/*.yaml`. Each strategy lists which indicators are `enabled`, their `params`, and `risk` settings (`start_cash`, `risk_per_trade`, `stop_loss_pct`, `slippage`). `exclude_categories: [crypto]` skips a ticker category automatically.

LLM optimization writes tuned copies to `stonkslib/strategies/optimized/`. Use `--per-ticker` to save per-ticker YAMLs instead of global. Use `--leaps` to score by avg trade % (options-appropriate) and save LEAP-specific YAMLs.

Default Ollama model for optimization: `qwen2.5:7b`. Use `--model qwen2.5:32b` for better results (slower). Ollama must be running (`ollama serve`).

### LEAP backtest design notes

- **Pricing**: Black-Scholes using 30-bar rolling realized vol as IV proxy; VIX rank used as market-wide IV environment indicator
- **Position sizing**: Fixed at `start_cash * risk_per_trade` (not compounding cash) to prevent astronomical P&L from many trades
- **Exits**: Stop-loss at 50% premium loss OR expiry (< 14 days remaining). No signal-based exits — user decides when to exit
- **Option type `auto`**: picks call/put per signal direction (BUY signal → call, SELL signal → put)
- **Results scored by** `avg_pnl_pct` (avg % return per trade), not net P&L, to avoid premium-size bias

### Dashboard (Streamlit)

Launched via the `stonks-dash` systemd service (restart with
`systemctl --user restart stonks-dash` after dashboard code changes; the
`stonks-bot` service is the separate Discord bot). Sidebar navigation/sections are
defined explicitly in `stonkslib/dash/app.py` via `st.navigation({...})` — the
numeric filename prefixes under `pages/` are cosmetic, only the `title=` and
section key drive the sidebar. Pages under `stonkslib/dash/pages/`:

| Page | File | Notes |
|---|---|---|
| Home | `0_Home.py` | Quick-start guide, glossary |
| Watchlist | `6_Watchlist.py` | Price, day change, volume, signal badge, earnings countdown, freshness |
| Alerts | `9_Alerts.py` | Full watchlist signal scan; results saved to `data/last_alert.json` |
| Confluence | `2_Confluence.py` | Multi-indicator signal heatmap; vectorized `str.contains()` for performance |
| Chart | `1_Chart.py` | OHLCV + indicators + earnings overlays (beat/miss vlines, forward markers) |
| Signals | `3_Signals.py` | Per-indicator signal table |
| Backtest | `4_Backtest.py` | Run + compare backtests |
| Trades | `5_Trades.py` | Entry/exit log from a saved backtest |
| Alpaca | `8_Alpaca.py` | Live Alpaca account — equity curve, positions, orders, watchlist sync; paper/live toggle |
| Robinhood | `12_Robinhood.py` | Live Robinhood account (read-only) — equity, positions, orders via the SnapTrade aggregator; shows a connect link until linked |
| Pipeline | `7_Pipeline.py` | Trigger fetch/clean/analyze from the UI |
| News | `10_News.py` | Finnhub headlines + sentiment per ticker; cached 4h; requires FINNHUB_API_KEY |

Key dashboard patterns:
- `@st.cache_data(ttl=3600)` on all data-loading functions; indicator functions take `(ticker, interval, *params)` as hashable cache keys, never DataFrames
- All widgets have page-prefixed `key=` so state survives navigation (e.g. `key="chart_ticker"`)
- Alert results: stored in `st.session_state` + `data/last_alert.json`; pages load from session first, fall back to disk
- Earnings overlays on Chart: dotted vlines colored green (beat) / red (miss) / grey (no surprise data); next earnings = orange dashed; forward markers (+15/30/45d) = light blue dashed

### Discord bot commands

```
!leaps [interval]          # scan watchlist for LEAP opportunities
!leaps-backtest NVDA call  # run LEAP backtest
!leaps-trades NVDA         # show entry/exit dates
!optimize NVDA leaps call  # LEAP-specific optimization
!alert [interval]          # regular signal scan
!backtest NVDA [strategy]
!help
```

### Config files

- **`tickers.yaml`** — watchlist grouped by category (`stocks`, `etfs`, `crypto`)
- **`config.yaml`** — canonical paths (`ticker_data_dir`, `options_data_dir`, `strategy_dir`, etc.) and options strategy parameters
- **`.env`** — `STONKS_DISCORD_WEBHOOK`, `DISCORD_BOT_TOKEN`, `FINNHUB_API_KEY`, Alpaca keys (`ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, optional `ALPACA_LIVE_*`), SnapTrade (`SNAPTRADE_CLIENT_ID`/`SNAPTRADE_CONSUMER_KEY`, for Robinhood) (gitignored)

### Brokers

Each broker is a module under `stonkslib/broker/` and gets its **own dashboard
page** grouped in the **"Portfolio"** nav section — the connection models differ
too much for one shared page (Alpaca = REST + keys + paper/live; Robinhood = via
the SnapTrade aggregator, read-only; IBKR = socket to a running TWS/Gateway,
planned next). Every broker module returns the **same canonical schema** so the
shared renderers in `dash/common.py` (`render_account_metrics`,
`render_positions_table`, `render_orders_table`) work across all pages:
- positions: `symbol, qty, avg_cost, market_value, unrealized_pnl, unrealized_pnl_pct`
- orders: `symbol, side, qty, filled_qty, type, status, submitted, filled_avg`

**Robinhood via SnapTrade.** Robinhood has no official API, so
`broker/snaptrade.py` is a hand-rolled signed REST client (HMAC-SHA256 over
sorted-keys JSON `{content, path, query}` in the `Signature` header; base URL
`https://api.snaptrade.com/api/v1`; every request adds `clientId` + `timestamp`).
Do **not** use the `snaptrade-python-sdk` — it fails to import on Python 3.13.
`.env` needs `SNAPTRADE_CLIENT_ID` + `SNAPTRADE_CONSUMER_KEY`; the per-user
`userSecret` is generated by `register_user()` and stored in gitignored
`data/snaptrade_user.json` (chmod 600). Linking a brokerage is a one-time browser
step via `connection_portal_url()` (the Robinhood page exposes a "Generate
connection link" button). `broker/robinhood.py` adapts SnapTrade's Robinhood
account(s) — both Individual and Crypto are merged — to the canonical schema:
ticker = `position.symbol.symbol.symbol`, `units` = qty, `average_purchase_price`,
`price` (market_value = units×price), `open_pnl`. Read-only — no order placement.
