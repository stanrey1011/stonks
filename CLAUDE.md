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

### Systemd (Discord bot)
```sh
systemctl --user restart stonks-bot          # after code changes
systemctl --user start stonks-alert.service  # trigger alert scan now
journalctl --user -u stonks-bot -f
```

### Daily cron (scripts/daily_alert.sh)
Runs at 20:30 UTC weekdays (4:30pm ET). Runs `stonks alert` then `stonks leaps all --interval 1wk` and posts both to Discord webhook. Crontab: `30 20 * * 1-5 /home/as/stonks/scripts/daily_alert.sh`

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
- **`stonkslib/owui_tool.py`** — Open WebUI Tools class (install via Workspace → Tools); exposes all CLI features including LEAP tools to the LLM chat interface

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
- **`.env`** — `STONKS_DISCORD_WEBHOOK` and `DISCORD_BOT_TOKEN` (gitignored)
