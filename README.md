# Stonks

A local-first quantitative trading toolkit for stocks, ETFs, and crypto. Fetches and cleans OHLCV data from Yahoo Finance, runs technical indicator analysis, backtests YAML-defined strategies, optimizes parameters via local LLM (Ollama), and delivers daily trade alerts to Discord — all from a single CLI.

---

## Features

- **Data pipeline** — fetch, clean, and analyze OHLCV data for any ticker/interval
- **Technical indicators** — RSI, MACD, Bollinger Bands, OBV, SMA/EMA double & triple, Fibonacci
- **Chart patterns** — Head & Shoulders, Triangles, Double tops/bottoms, Wedges
- **YAML strategies** — define indicator combos, thresholds, and risk params in plain text
- **Backtesting** — realistic fills at next bar open with configurable slippage
- **LLM optimization** — Ollama-driven parameter tuning across strategies and tickers
- **Daily alerts** — cron-scheduled signal scan posts BUY/SELL alerts to Discord
- **Discord bot** — manage watchlist, run scans, and kick off optimization from chat
- **Streamlit dashboard** — interactive candlestick charts with indicator overlays

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

Edit `tickers.yaml` to set your watchlist:

```yaml
stocks:
  - AAPL
  - MSFT
crypto:
  - BTC-USD
  - ETH-USD
etfs:
  - SPY
  - QQQ
```

Or manage it from the CLI:
```sh
stonks tickers add AMZN
stonks tickers add SOL-USD --category crypto
stonks tickers remove MSFT
stonks tickers list
```

### 2. Configure Discord (optional)

Create a `.env` file in the project root:

```sh
STONKS_DISCORD_WEBHOOK=https://discord.com/api/webhooks/...
DISCORD_BOT_TOKEN=your.bot.token.here
```

---

## CLI Reference

### Data Pipeline

```sh
stonks fetch --all-tickers --interval 1d      # fetch raw OHLCV from Yahoo Finance
stonks clean --all-tickers --interval 1d      # clean and standardize
stonks analyze --all-tickers --interval 1d    # run indicators and pattern detection
stonks merge --all-tickers --interval 1d      # combine into single CSV per ticker
```

### Backtesting

```sh
stonks backtest --strategy rsi.yaml --ticker AAPL --interval 1d
stonks backtest --all-strategies --all-tickers --interval 1d
```

Strategies live in `stonkslib/strategies/`. Each YAML defines enabled indicators, thresholds, and risk params (position size, stop loss, slippage).

### LLM Optimization

Uses a local Ollama model to iteratively improve strategy parameters based on backtest results.

```sh
stonks optimize --strategy rsi.yaml --ticker AAPL --iterations 5
stonks optimize --all-strategies --all-tickers --iterations 3
stonks optimize --strategy rsi.yaml --all-tickers --model qwen2.5:32b
```

Optimized YAMLs are saved to `stonkslib/strategies/optimized/`.

### Alerts

```sh
stonks alert --strategy rsi.yaml --all-tickers
stonks alert --all-strategies --all-tickers --use-optimized
stonks alert --all-strategies --all-tickers --webhook-url $STONKS_DISCORD_WEBHOOK
```

Only fires to Discord when signals exist.

### Watchlist

```sh
stonks tickers list
stonks tickers add AMD
stonks tickers add SOL-USD --category crypto
stonks tickers remove TSLA
stonks tickers announce           # post full watchlist to Discord
```

Adding or removing a ticker automatically notifies Discord.

### Discord Bot

```sh
stonks bot          # start the bot (or use systemd service)
```

Bot commands (in Discord):
```
!help
!tickers
!tickers add AMZN
!tickers add SOL-USD crypto
!tickers remove TSLA
!alert
!alert AAPL
!optimize AAPL
!optimize
```

### Dashboard

```sh
streamlit run stonkslib/dash/dashboard.py
```

---

## Automated Daily Alerts

Runs via a systemd user timer — no cron needed.

```sh
systemctl --user enable stonks-alert.timer
systemctl --user start stonks-alert.timer
```

Fires every weekday at 4:30pm ET (20:30 UTC). Fetches fresh data, scans all strategies, posts to Discord if signals fire.

```sh
systemctl --user list-timers                  # check next scheduled run
systemctl --user start stonks-alert.service   # trigger manually anytime
```

---

## Running the Bot as a Service

The bot runs as a systemd user service so it stays alive without a terminal:

```sh
systemctl --user enable stonks-bot
systemctl --user start stonks-bot
systemctl --user status stonks-bot
journalctl --user -u stonks-bot -f    # live logs
```

---

## Strategies

Strategies are defined in `stonkslib/strategies/*.yaml`:

```yaml
name: RSI Only
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

Available indicators: `rsi`, `macd`, `bollinger`, `ma_double`

---

## yfinance Intervals & Lookback Limits

| Interval | Stocks/ETFs         | Crypto              |
|----------|---------------------|---------------------|
| `1m`     | 7 days              | 7–60 days           |
| `5m`     | 60 days             | 60 days             |
| `15m`    | 60 days             | 60 days             |
| `1h`     | ~2 years            | ~2 years            |
| `1d`     | Full history        | Full history        |
| `1wk`    | Full history        | Full history        |

---

## Folder Structure

```
stonks/
├── stonkslib/
│   ├── alerts/         # Signal detection logic
│   ├── backtest/       # Backtesting engines
│   ├── bot/            # Discord bot
│   ├── cli/            # CLI commands
│   ├── dash/           # Streamlit dashboard
│   ├── indicators/     # RSI, MACD, Bollinger, MA, OBV, Fibonacci
│   ├── llm/            # Ollama optimization loop
│   ├── patterns/       # Chart pattern detectors
│   ├── strategies/     # YAML strategy configs
│   └── utils/          # Shared helpers
├── data/               # Fetched/cleaned data (gitignored)
├── scripts/            # daily_alert.sh cron script
├── tickers.yaml        # Your watchlist
├── .env                # Discord webhook + bot token (gitignored)
└── requirements.txt
```

---

## License

MIT
