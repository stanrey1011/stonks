import discord
import yaml
import os
import asyncio
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
STRATEGY_DIR = PROJECT_ROOT / "stonkslib" / "strategies"

HELP_TEXT = """**Stonks Bot — Commands & Workflows**

**── Watchlist ──**
`!tickers` — show current watchlist
`!tickers add AMZN` — add a stock (also fetches & cleans data automatically)
`!tickers add SOL-USD crypto` — add crypto (categories: stocks, crypto, etfs)
`!tickers remove TSLA` — remove a ticker

**── Signals ──**
`!alert` — scan all tickers across all strategies right now
`!alert AAPL` — scan a single ticker

**── Optimization ──**
`!optimize AAPL` — tune strategy params for one ticker using LLM (3 iterations)
`!optimize` — tune across all tickers — slow, run overnight

**── Workflows ──**
📈 **New ticker:** `!tickers add AMD` → data is fetched automatically → `!alert AMD` to check signals
🔍 **Daily check:** `!alert` → signals posted if any fire (also runs automatically at 4:30pm ET)
⚙️ **Tune strategies:** `!optimize AAPL` → wait a few minutes → `!alert` uses updated params
🧹 **Drop a ticker:** `!tickers remove TSLA` → removed from all future scans

`!help` — show this message
"""


def _load_tickers():
    with open(TICKER_YAML) as f:
        return yaml.safe_load(f) or {}


def _save_tickers(data):
    with open(TICKER_YAML, "w") as f:
        yaml.dump(data, f, default_flow_style=False)


def _watchlist_text(data):
    lines = ["**Stonks Watchlist**"]
    for category, items in data.items():
        if items:
            tickers_str = "  ".join(f"`{t}`" for t in items)
            lines.append(f"**{category.capitalize()}:** {tickers_str}")
    return "\n".join(lines)


def _pipeline(ticker, interval="1d"):
    from stonkslib.fetch.td import fetch_all
    from stonkslib.clean.td import clean_td
    from stonkslib.merge.by_indicators import merge_signals_for_ticker_interval

    fetch_all(
        yaml_file=PROJECT_ROOT / "tickers.yaml",
        data_dir=PROJECT_ROOT / "data" / "ticker_data" / "raw",
        tickers=[ticker],
    )
    clean_td(ticker, interval)
    merge_signals_for_ticker_interval(ticker, interval)


def run_bot(token):
    intents = discord.Intents.none()
    intents.guilds = True
    intents.guild_messages = True
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        guilds = [g.name for g in client.guilds]
        print(f"[✓] Stonks bot online as {client.user}")
        print(f"    Servers: {guilds if guilds else 'NONE — bot not in any server'}")

    @client.event
    async def on_message(message):
        if message.author.bot:
            return
        if not message.content.startswith("!"):
            return

        parts = message.content.strip().split()
        cmd = parts[0].lower()

        # --- !help ---
        if cmd == "!help":
            await message.channel.send(HELP_TEXT)

        # --- !tickers ---
        elif cmd == "!tickers":
            if len(parts) == 1:
                data = _load_tickers()
                await message.channel.send(_watchlist_text(data))

            elif parts[1].lower() == "add" and len(parts) >= 3:
                ticker = parts[2].upper()
                category = parts[3].lower() if len(parts) >= 4 else "stocks"
                if category not in ["stocks", "crypto", "etfs"]:
                    await message.channel.send(f"[!] Unknown category `{category}` — use stocks, crypto, or etfs")
                    return
                data = _load_tickers()
                data.setdefault(category, [])
                if ticker in data[category]:
                    await message.channel.send(f"`{ticker}` is already in {category}")
                    return
                data[category].append(ticker)
                _save_tickers(data)
                await message.channel.send(f"[+] Added `{ticker}` to {category}\n\n{_watchlist_text(data)}\n\nFetching data for `{ticker}`...")

                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, _pipeline, ticker)
                await message.channel.send(f"[✓] `{ticker}` is ready to scan.")

            elif parts[1].lower() == "remove" and len(parts) >= 3:
                ticker = parts[2].upper()
                data = _load_tickers()
                removed = False
                for category, items in data.items():
                    if items and ticker in items:
                        items.remove(ticker)
                        removed = True
                if not removed:
                    await message.channel.send(f"[!] `{ticker}` not found in watchlist")
                    return
                _save_tickers(data)
                await message.channel.send(f"[-] Removed `{ticker}`\n\n{_watchlist_text(data)}")

            else:
                await message.channel.send("Usage: `!tickers` | `!tickers add AMZN` | `!tickers remove TSLA`")

        # --- !alert ---
        elif cmd == "!alert":
            from stonkslib.alerts.signals import check_signals
            ticker_arg = parts[1].upper() if len(parts) >= 2 else None

            await message.channel.send("Scanning for signals...")

            data = _load_tickers()
            all_tickers = [t for items in data.values() for t in (items or [])]
            tickers = [ticker_arg] if ticker_arg else all_tickers

            strategy_paths = list(STRATEGY_DIR.glob("*.yaml"))
            all_signals = []

            for path in strategy_paths:
                opt_path = STRATEGY_DIR / "optimized" / f"{path.stem}_optimized.yaml"
                active_path = opt_path if opt_path.exists() else path
                with open(active_path) as f:
                    strat = yaml.safe_load(f)
                for t in tickers:
                    signals = check_signals(t, "1d", strat)
                    if signals:
                        for s in signals:
                            s["strategy"] = strat.get("name", path.stem)
                        all_signals.extend(signals)

            if not all_signals:
                await message.channel.send("No signals on the latest bar.")
                return

            buys = [s for s in all_signals if s["type"] == "BUY"]
            sells = [s for s in all_signals if s["type"] == "SELL"]
            lines = ["**Signal Scan Results**"]
            if buys:
                lines.append("\n**BUY signals**")
                for s in buys:
                    lines.append(f"> `{s['ticker']}` ${s['close']:.2f} — {s['reason']} _({s.get('strategy', '?')})_")
            if sells:
                lines.append("\n**SELL signals**")
                for s in sells:
                    lines.append(f"> `{s['ticker']}` ${s['close']:.2f} — {s['reason']} _({s.get('strategy', '?')})_")
            await message.channel.send("\n".join(lines))

        # --- !optimize ---
        elif cmd == "!optimize":
            ticker_arg = parts[1].upper() if len(parts) >= 2 else None
            await message.channel.send(
                f"Starting optimization for {'all tickers' if not ticker_arg else ticker_arg}... this may take a few minutes."
            )

            from stonkslib.llm.optimizer import optimize
            from stonkslib.backtest.strategy import load_strategy

            data = _load_tickers()
            all_tickers = [t for items in data.values() for t in (items or [])]
            tickers = [ticker_arg] if ticker_arg else all_tickers
            strategy_paths = list(STRATEGY_DIR.glob("*.yaml"))

            results = []
            for path in strategy_paths:
                strat_name = load_strategy(path).get("name", path.stem)
                result = optimize(strategy_path=path, tickers=tickers, interval="1d", iterations=3)
                if result and result.get("best_metrics"):
                    m = result["best_metrics"]
                    avg_pnl = sum(x["net_pnl"] for x in m) / len(m)
                    avg_win = sum(x["win_rate"] for x in m) / len(m)
                    results.append((strat_name, avg_pnl, avg_win))

            if not results:
                await message.channel.send("Optimization failed — is Ollama running?")
                return

            results.sort(key=lambda r: r[1], reverse=True)
            lines = ["**Optimization Results**"]
            for i, (name, pnl, win) in enumerate(results, 1):
                marker = " ◀ BEST" if i == 1 else ""
                lines.append(f"`{i}.` **{name}** — Avg P&L: ${pnl:.2f} | Win rate: {win:.1%}{marker}")
            await message.channel.send("\n".join(lines))

    client.run(token)
