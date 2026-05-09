# Stonks

A local-first quantitative trading toolkit for stocks, ETFs, and crypto. Fetches and cleans OHLCV data from Yahoo Finance, runs technical indicator analysis, backtests YAML-defined strategies, optimizes parameters via local LLM (Ollama), and delivers daily trade alerts to Discord — all from a single CLI.

---

## Features

- **Data pipeline** — fetch, clean, and analyze OHLCV data for any ticker/interval
- **One-shot pipeline** — `stonks pipeline AAPL` runs fetch → clean → analyze in one command
- **Technical indicators** — RSI, MACD, Bollinger Bands, EMA Crossover, Supertrend, RSI Divergence
- **Chart patterns** — Head & Shoulders, Triangles, Double tops/bottoms, Wedges
- **YAML strategies** — define indicator combos, thresholds, and risk params in plain text
- **Backtesting** — realistic fills at next bar open with configurable slippage
- **LLM optimization** — Ollama-driven parameter tuning; optimized YAMLs auto-applied on alert
- **Daily alerts** — systemd timer posts BUY/SELL signals to Discord every weekday at 4:30pm ET
- **Discord bot** — manage watchlist, run scans, backtest, and kick off optimization from chat
- **Data freshness view** — `stonks status` shows what data you have and what's been optimized

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
  - BBAI
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

All data commands accept a positional target: a ticker symbol, a category (`stocks`/`etfs`/`crypto`), or `all`. No flags needed.

### Quick Pipeline

```sh
stonks pipeline            # fetch → clean → analyze all tickers (1d)
stonks pipeline AAPL       # single ticker
stonks pipeline crypto     # all crypto
stonks pipeline all --interval 1wk --force
```

### Fetch

```sh
stonks fetch               # all tickers
stonks fetch AAPL          # single ticker (doesn't add to watchlist)
stonks fetch crypto        # all crypto
stonks fetch stocks --force
stonks fetch options buy leaps --ticker AAPL
```

Fetching a single ticker without `stonks tickers add` is good for quick one-off backtesting without polluting the watchlist.

### Clean

```sh
stonks clean               # all tickers, all intervals
stonks clean AAPL
stonks clean etfs --interval 1d
stonks clean options AAPL
```

### Analyze

```sh
stonks analyze             # all tickers (1d)
stonks analyze AAPL --interval 1wk
stonks analyze crypto
```

Runs indicators, detects patterns, and merges signals into combined CSVs.

### Backtest

```sh
stonks backtest AAPL --strategy rsi.yaml
stonks backtest all --all-strategies --interval 1d
stonks backtest stocks --all-strategies --interval 1wk
```

Prints a ranked summary table sorted by avg P&L. Optimized YAMLs are used automatically if present.

### Optimize

```sh
stonks optimize --strategy rsi.yaml --ticker AAPL --iterations 5
stonks optimize --all-strategies --all-tickers --iterations 3
stonks optimize --strategy rsi.yaml --all-tickers --model qwen2.5:32b
```

Uses local Ollama to iteratively tune strategy parameters. Saves results to `stonkslib/strategies/optimized/`.

### Alert

```sh
stonks alert all --all-strategies
stonks alert AAPL --strategy rsi.yaml --interval 1wk
stonks alert crypto --all-strategies
```

Scans the latest bar for entry/exit signals. Automatically uses optimized YAMLs when available. Posts to Discord via `STONKS_DISCORD_WEBHOOK`.

### Status

```sh
stonks status
```

Shows watchlist, data freshness per ticker/interval, and which strategies have been optimized.

### Discord Bot

```sh
stonks bot
```

Bot commands in Discord:

| Command | What it does |
|---|---|
| `!help` | Show all commands |
| `!tickers` | Show watchlist |
| `!tickers add AMZN` | Add stock to watchlist + run pipeline |
| `!tickers add SOL-USD crypto` | Add crypto |
| `!tickers remove TSLA` | Remove from watchlist |
| `!alert` | Scan all tickers now |
| `!alert AAPL 1wk` | Scan single ticker, weekly interval |
| `!backtest AAPL` | Backtest all strategies for a ticker |
| `!backtest AAPL 1wk` | Weekly backtest |
| `!optimize AAPL` | Optimize strategies for a ticker |
| `!optimize` | Optimize everything |

---

## Automation

Both run automatically via systemd — no terminal needed.

```sh
# Enable on first run
systemctl --user enable stonks-bot
systemctl --user enable stonks-alert.timer
systemctl --user start stonks-bot
systemctl --user start stonks-alert.timer

# Day-to-day management
systemctl --user status stonks-bot
systemctl --user restart stonks-bot          # after code changes
systemctl --user start stonks-alert.service  # trigger alert scan now
journalctl --user -u stonks-bot -f           # live bot logs
journalctl --user -u stonks-alert -f         # alert scan logs
```

Alert timer fires every weekday at 20:30 UTC (4:30pm ET).

---

## Strategies

Defined in `stonkslib/strategies/*.yaml`. Edit params directly or run `stonks optimize` to let the LLM tune them. Optimized YAMLs are auto-applied during alert and backtest runs.

| Strategy | File | Notes |
|---|---|---|
| RSI Only | `rsi.yaml` | Clean and consistent across equities |
| RSI + MACD | `rsi_macd.yaml` | Good for trending markets |
| Bollinger + RSI | `bollinger.yaml` | Both must agree (AND logic) |
| EMA Crossover | `ema_crossover.yaml` | 9/21 EMA, tight stop |
| MA Crossover | `ma_crossover.yaml` | 20/50 EMA, no patterns |
| Supertrend | `supertrend.yaml` | ATR-based; **excludes crypto** |
| RSI Divergence | `rsi_divergence.yaml` | Price/RSI disagreement signals |

Strategies support `exclude_categories: [crypto]` to skip categories automatically.

Example strategy YAML:

```yaml
name: RSI Only
exclude_categories: []
indicators:
  rsi:
    enabled: true
    params:
      period: 14
      overbought: 70
      oversold: 30
risk:
  start_cash: 10000
  risk_per_trade: 0.2
  stop_loss_pct: 0.1
  slippage: 0.0005
```

---

## Data Lookback (yfinance)

Historical data is fetched at 10 years for daily and weekly intervals to capture major market events (COVID crash, 2022 bear market).

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
│   ├── backtest/       # Backtesting engine (strategy.py)
│   ├── bot/            # Discord bot
│   ├── cli/            # CLI commands
│   ├── dash/           # Streamlit dashboard
│   ├── indicators/     # RSI, MACD, Bollinger, MA, Supertrend, RSI Divergence
│   ├── llm/            # Ollama optimization loop
│   ├── patterns/       # Chart pattern detectors
│   ├── strategies/     # YAML strategy configs
│   │   └── optimized/  # LLM-tuned YAMLs (auto-generated)
│   └── utils/          # Shared helpers
├── data/               # Fetched/cleaned data (gitignored)
├── scripts/            # daily_alert.sh
├── tickers.yaml        # Watchlist
├── .env                # Discord webhook + bot token (gitignored)
└── requirements.txt
```

---

## Roadmap

- [ ] News + sentiment layer in alerts
- [ ] Interactive Brokers paper trading via `ib_insync`
- [ ] LEAPS options backtesting via ThetaData
- [ ] OpenClaw / LLM natural language query integration

---

## License

MIT
