# Stonks

A local-first quantitative trading toolkit for stocks, ETFs, and crypto. Fetches and cleans OHLCV data from Yahoo Finance, runs technical indicator analysis, backtests YAML-defined strategies, optimizes parameters via local LLM (Ollama), scans for LEAP options opportunities, and delivers daily trade alerts to Discord — all from a single CLI.

---

## Features

- **Data pipeline** — fetch, clean, and analyze OHLCV data for any ticker/interval
- **One-shot pipeline** — `stonks pipeline AAPL` runs fetch → clean → analyze in one command
- **Technical indicators** — RSI, MACD, Bollinger Bands, EMA Crossover, Supertrend, RSI Divergence
- **Chart patterns** — Head & Shoulders, Triangles, Double tops/bottoms, Wedges
- **YAML strategies** — define indicator combos, thresholds, and risk params in plain text
- **Backtesting** — realistic fills at next bar open with configurable slippage
- **Per-ticker optimization** — Ollama-driven parameter tuning; saves per-ticker YAMLs to avoid cross-ticker skew
- **LEAP options scanner** — VIX rank as IV proxy + live options chain; ranks call/put opportunities across watchlist
- **LEAP backtesting** — Black-Scholes simulation; exits on stop-loss or expiry only (you decide when to sell)
- **LEAP optimization** — scores strategies by avg trade % return (not net P&L) for options-appropriate tuning
- **Daily alerts** — scheduled scan posts BUY/SELL signals + LEAP scan to logs every weekday at 4:30pm ET (Matrix push alerts planned)
- **Open WebUI tool** — all features accessible via the LLM chat interface (install `owui_tool.py` as a Tool)
- **Data freshness view** — `stonks status` shows what data you have and what's been optimized

---

## Daily Use

```sh
# Check signals right now
cd /home/as/stonks && source venv/bin/activate
stonks alert all --all-strategies       # uses optimized YAMLs automatically

# Full pipeline for everything
stonks pipeline                          # 1d
stonks pipeline all --interval 1wk

# Add / remove a ticker
stonks tickers add AMD stocks
stonks tickers add SOL-USD crypto
stonks tickers remove TSLA

# Data freshness + what's optimized
stonks status
```

> **Tip:** `stonks fetch AAPL` without `stonks tickers add` is useful for quick one-off backtesting without polluting the watchlist.

---

## Quick Start

```sh
git clone https://github.com/stanrey1011/stonks
cd stonks
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

> **Note:** Requires Python 3.13. Python 3.14 is not yet compatible with numpy.

---

## Setup

### 1. Configure tickers

Edit `tickers.yaml`:

```yaml
stocks:
  - AAPL
  - TSLA
  - NVDA
  - MSFT
etfs:
  - SPY
  - QQQ
crypto:
  - BTC-USD
  - ETH-USD
```

Or manage from the CLI (auto-runs pipeline + posts to Discord):

```sh
stonks tickers add AMZN stocks
stonks tickers add SOL-USD crypto
stonks tickers remove MSFT
stonks tickers list
stonks tickers announce       # post full watchlist to Discord
```

### 2. Configure Discord (optional)

Create a `.env` file in the project root:

```sh
STONKS_DISCORD_WEBHOOK=https://discord.com/api/webhooks/...
DISCORD_BOT_TOKEN=your.bot.token.here
```

---

## CLI Reference

All data commands accept a positional target: a ticker symbol, a category (`stocks`/`etfs`/`crypto`), or `all`.

### Pipeline

```sh
stonks pipeline            # fetch → clean → analyze all tickers (1d)
stonks pipeline AAPL       # single ticker
stonks pipeline crypto     # all crypto
stonks pipeline all --interval 1wk --force
```

### Fetch / Clean / Analyze

```sh
stonks fetch               # all tickers
stonks fetch AAPL          # single ticker (doesn't add to watchlist)
stonks clean AAPL --interval 1d
stonks analyze all --interval 1wk
```

### Backtest

```sh
stonks backtest AAPL --strategy rsi.yaml
stonks backtest all --all-strategies --interval 1d
stonks backtest stocks --all-strategies --interval 1wk
```

Prints a ranked summary table sorted by net P&L. Optimized YAMLs are used automatically if present.

### Optimize

```sh
# Global optimized YAML (one file per strategy)
stonks optimize --all-strategies --all-tickers --iterations 3

# Per-ticker YAMLs (avoids cross-ticker parameter skew)
stonks optimize --all-strategies --per-ticker --all-tickers --iterations 3

# LEAP-specific per-ticker optimization (scores by avg trade %, not net P&L)
stonks optimize --all-strategies --per-ticker --leaps --option-type call --all-tickers
stonks optimize --all-strategies --per-ticker --leaps --option-type put --all-tickers
```

Uses local Ollama to iteratively tune strategy parameters. Requires `ollama serve`. Default model: `qwen2.5:7b`. Use `--model qwen2.5:32b` for better results (slower).

**Ollama models available on `anton`:**
- `qwen2.5:0.5b`, `qwen2.5:7b`, `qwen2.5:32b`
- `llama3.3:70b`
- `glm-4.7-flash`

### Alert

```sh
stonks alert all --all-strategies
stonks alert AAPL --strategy rsi.yaml --interval 1wk
stonks alert crypto --all-strategies
```

Scans the latest bar for entry/exit signals. Per-ticker optimized YAMLs are used automatically. Posts to Discord via `STONKS_DISCORD_WEBHOOK`.

### LEAP Options

```sh
# Scan watchlist for LEAP opportunities (VIX rank + live options chain)
stonks leaps stocks
stonks leaps all --interval 1wk --webhook-url $STONKS_DISCORD_WEBHOOK

# Backtest LEAP strategies using Black-Scholes pricing
stonks leaps-backtest NVDA --option-type call --interval 1wk
stonks leaps-backtest NVDA --option-type auto   # picks call/put per signal direction
stonks leaps-backtest NVDA --option-type put --stop-loss 0.4

# Show entry/exit trade log (to verify on a chart)
stonks leaps-trades NVDA
stonks leaps-trades NVDA --option-type call --strategy supertrend
stonks leaps-trades NVDA --option-type put --strategy "rsi macd"
```

LEAP exits are stop-loss (50% premium loss) or expiry only — no automatic signal-based exits.

### Status

```sh
stonks status
```

Shows watchlist, data freshness per ticker/interval, and which strategies have been optimized.

---

## Notifications

Discord bot and webhook alerts are removed. Alert scans print to stdout and log files. **Matrix integration is planned** — a self-hosted Matrix server will replace Discord for push alerts.

---

## Automation

Scheduled jobs run via systemd (host) or Docker supercronic (container).

```sh
# Host systemd (Anton)
systemctl --user enable stonks-alert.timer
systemctl --user start stonks-alert.service  # trigger now
journalctl --user -u stonks-alert -f         # live logs

# Docker
docker compose -f docker-compose.yml up -d   # prod (baked image)
docker compose up                            # dev (source live-mounted)
docker compose exec stonks-scheduler stonks pipeline AAPL --interval 1d
docker compose logs stonks-scheduler -f
```

Alert timer fires every weekday at 20:30 UTC (4:30pm ET). Runs signal scan + LEAP scan, outputs to log.

---

## Open WebUI

Install `stonkslib/owui_tool.py` as a Tool in Open WebUI (Workspace → Tools → paste file content). Exposes all features to the LLM chat interface:

| Tool | What it does |
|---|---|
| `get_watchlist` | Show current watchlist |
| `add_ticker` / `remove_ticker` | Manage watchlist |
| `scan_ticker` / `scan_watchlist` | BUY/SELL signals |
| `backtest_ticker` | Strategy backtest |
| `optimize_ticker` | Per-ticker LLM optimization |
| `get_trades` | Strategy trade log |
| `scan_leaps` | LEAP opportunity scan |
| `leaps_backtest` | LEAP backtest |
| `get_leaps_trades` | LEAP entry/exit dates |
| `optimize_leaps` | LEAP-specific optimization |

---

## Strategies

Defined in `stonkslib/strategies/*.yaml`. Edit params directly or run `stonks optimize` to let the LLM tune them.

| Strategy | File | Notes |
|---|---|---|
| RSI Only | `rsi.yaml` | Clean and consistent across equities |
| RSI + MACD | `rsi_macd.yaml` | Good for trending markets |
| Bollinger + RSI | `bollinger.yaml` | Both must agree (AND logic) |
| EMA Crossover | `ema_crossover.yaml` | 9/21 EMA, tight stop |
| MA Crossover | `ma_crossover.yaml` | 20/50 EMA, no patterns |
| Supertrend | `supertrend.yaml` | ATR-based; **excludes crypto** |
| RSI Divergence | `rsi_divergence.yaml` | Price/RSI disagreement signals |

**ThinkOrSwim reference params (from backtests):**
- RSI Only: Period 14, Oversold 30, Overbought 70, Daily
- RSI + MACD: RSI Period 7, Oversold 30, Overbought 78 / MACD 10-26-9, Stop 12%

Optimized YAMLs are saved to `stonkslib/strategies/optimized/`. The lookup priority is:
1. `{name}_{ticker}_leaps_{type}_optimized.yaml` — LEAP-specific per-ticker
2. `{name}_{ticker}_optimized.yaml` — per-ticker
3. `{name}_optimized.yaml` — global
4. `{name}.yaml` — base

---

## LEAP Backtest Design

- **Pricing**: Black-Scholes using 30-bar rolling realized volatility as IV proxy
- **IV environment**: VIX 52-week percentile rank shown in scanner output
- **Position sizing**: Fixed at `start_cash × risk_per_trade` (not compounding) — prevents unrealistic exponential growth
- **Exits**: Stop-loss at 50% premium loss OR expiry (< 14 days remaining). No signal-based exits
- **`--option-type auto`**: picks call on BUY signals, put on SELL signals
- **Optimization scoring**: avg % return per trade (not net P&L) to avoid premium-size bias

---

## Data Lookback (yfinance)

| Interval | Lookback |
|---|---|
| `1m` | 7 days |
| `5m` / `15m` / `30m` | 60 days |
| `1h` | ~2 years |
| `1d` | 10 years |
| `1wk` | 10 years |

---

## Folder Structure

```
stonks/
├── stonkslib/
│   ├── alerts/         # Signal detection logic
│   ├── backtest/       # strategy.py (equity) + leaps.py (Black-Scholes)
│   ├── bot/            # Discord bot
│   ├── cli/            # CLI commands
│   ├── dash/           # Streamlit dashboard
│   ├── indicators/     # RSI, MACD, Bollinger, MA, Supertrend, RSI Divergence
│   ├── leaps/          # LEAP scanner (VIX rank + live options chain)
│   ├── llm/            # Ollama optimization loop
│   ├── patterns/       # Chart pattern detectors
│   ├── strategies/     # YAML strategy configs
│   │   └── optimized/  # LLM-tuned YAMLs (auto-generated, gitignored)
│   ├── utils/          # Shared helpers
│   └── owui_tool.py    # Open WebUI Tools class
├── data/               # Fetched/cleaned data (gitignored)
├── scripts/            # daily_alert.sh (cron)
├── tickers.yaml        # Watchlist
├── .env                # Discord webhook + bot token (gitignored)
└── requirements.txt
```

---

## Roadmap

- [ ] News + sentiment layer in alerts
- [ ] Interactive Brokers paper trading via `ib_insync`
- [x] LEAP options backtesting (Black-Scholes; ThetaData not used)
- [x] Open WebUI / LLM chat integration (`owui_tool.py`)

---

## License

MIT
