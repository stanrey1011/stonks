import discord
import yaml
import os
import asyncio
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
STRATEGY_DIR = PROJECT_ROOT / "stonkslib" / "strategies"

VALID_INTERVALS = ["1d", "1wk", "1h", "1m", "5m", "15m", "30m"]

HELP_TEXT = """**Stonks Bot — Commands**

**── Watchlist ──**
`!tickers` — show watchlist
`!tickers add AMZN stocks` — add a stock (categories: stocks, etfs, crypto)
`!tickers add SOL-USD crypto`
`!tickers remove TSLA` — remove a ticker

**── Signals ──**
`!alert` — scan all tickers, all strategies (daily)
`!alert 1wk` — weekly scan (recommended before buying LEAPs)
`!alert AAPL` — single ticker daily scan
`!alert AAPL 1wk` — single ticker weekly

**── LEAP Options ──**
`!leaps` — scan all tickers for LEAP call/put opportunities (VIX + signals)
`!leaps etfs` — ETFs only (VIX most accurate here)
`!leaps AAPL` — single ticker LEAP scan
`!leaps 1wk` — weekly interval (default)
`!leaps-backtest AAPL` — backtest LEAP calls + puts on AAPL (weekly, auto)
`!leaps-backtest AAPL call` — calls only
`!leaps-backtest AAPL 1wk put` — weekly put backtest
`!leaps-trades NVDA call` — show entry/exit dates for best call strategy on NVDA
`!leaps-trades NVDA call supertrend` — specific strategy trade log

**── Backtesting ──**
`!backtest AAPL` — all strategies on AAPL (daily)
`!backtest AAPL 1wk` — weekly backtest
`!backtest` — all strategies, all tickers (daily)
`!trades AAPL rsi` — trade log for a strategy (run backtest first)
`!trades AAPL 1wk rsi only` — weekly trade log

**── Optimization ──**
`!optimize AAPL` — tune strategy params for AAPL (equity, daily, 3 iters)
`!optimize AAPL 1wk` — tune on weekly bars
`!optimize AAPL leaps call` — tune specifically for LEAP call entries on AAPL
`!optimize AAPL leaps put` — tune for LEAP put / hedge entries
`!optimize` — tune across all tickers (slow, run overnight)

**── Workflows ──**
📈 **New ticker:** `!tickers add AMD stocks` → auto-fetched → `!alert AMD`
🔍 **Daily routine:** `!alert` fires automatically at 4:30pm ET on weekdays
📅 **LEAP research:** `!leaps 1wk` → `!leaps-backtest NVDA call` → buy if confirmed
⚙️ **Tune for LEAPs:** `!optimize NVDA leaps call` → wait → `!leaps` uses updated params
🧹 **Drop a ticker:** `!tickers remove TSLA`

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


def _resolve_strategy(path, ticker=None, option_type=None):
    """Prefer LEAP-specific → ticker-specific → global optimized → base."""
    opt_dir = STRATEGY_DIR / "optimized"
    if ticker and option_type:
        p = opt_dir / f"{path.stem}_{ticker}_leaps_{option_type}_optimized.yaml"
        if p.exists():
            return p
    if ticker:
        p = opt_dir / f"{path.stem}_{ticker}_optimized.yaml"
        if p.exists():
            return p
    if option_type:
        p = opt_dir / f"{path.stem}_leaps_{option_type}_optimized.yaml"
        if p.exists():
            return p
    p = opt_dir / f"{path.stem}_optimized.yaml"
    return p if p.exists() else path


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


def _send_chunks(lines, max_len=1900):
    """Split a list of lines into chunks under Discord's 2000-char limit."""
    chunks, chunk = [], []
    for line in lines:
        if sum(len(l) + 1 for l in chunk) + len(line) > max_len:
            chunks.append("\n".join(chunk))
            chunk = []
        chunk.append(line)
    if chunk:
        chunks.append("\n".join(chunk))
    return chunks


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

        # ── !help ────────────────────────────────────────────────────────────
        if cmd == "!help":
            await message.channel.send(HELP_TEXT)

        # ── !tickers ─────────────────────────────────────────────────────────
        elif cmd == "!tickers":
            if len(parts) == 1:
                data = _load_tickers()
                await message.channel.send(_watchlist_text(data))

            elif parts[1].lower() == "add" and len(parts) >= 3:
                ticker = parts[2].upper()
                if len(parts) < 4:
                    await message.channel.send(
                        f"[!] Specify a category: `!tickers add {ticker} stocks` | `crypto` | `etfs`"
                    )
                    return
                category = parts[3].lower()
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
                await message.channel.send(
                    f"[+] Added `{ticker}` to {category}\n\n{_watchlist_text(data)}\n\nFetching data..."
                )
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
                await message.channel.send("Usage: `!tickers` | `!tickers add AMZN stocks` | `!tickers remove TSLA`")

        # ── !alert [ticker|interval] ──────────────────────────────────────────
        elif cmd == "!alert":
            from stonkslib.alerts.signals import check_signals

            ticker_arg = None
            interval = "1d"
            for p in parts[1:]:
                if p.lower() in VALID_INTERVALS:
                    interval = p.lower()
                else:
                    ticker_arg = p.upper()

            await message.channel.send(f"Scanning for signals (`{interval}`)...")

            data = _load_tickers()
            all_tickers = [t for items in data.values() for t in (items or [])]
            tickers = [ticker_arg] if ticker_arg else all_tickers
            strategy_paths = list(STRATEGY_DIR.glob("*.yaml"))
            all_signals = []

            for path in strategy_paths:
                for t in tickers:
                    active = _resolve_strategy(path, ticker=t)
                    with open(active) as f:
                        strat = yaml.safe_load(f)
                    signals = check_signals(t, interval, strat)
                    if signals:
                        for s in signals:
                            s["strategy"] = strat.get("name", path.stem)
                        all_signals.extend(signals)

            if not all_signals:
                await message.channel.send(f"No signals on the latest `{interval}` bar.")
                return

            buys = [s for s in all_signals if s["type"] == "BUY"]
            sells = [s for s in all_signals if s["type"] == "SELL"]
            lines = [f"**Signal Scan** (`{interval}`)"]
            if buys:
                lines.append("\n**BUY signals**")
                for s in buys:
                    lines.append(f"> `{s['ticker']}` ${s['close']:.2f} — {s['reason']} _({s.get('strategy', '?')})_")
            if sells:
                lines.append("\n**SELL signals**")
                for s in sells:
                    lines.append(f"> `{s['ticker']}` ${s['close']:.2f} — {s['reason']} _({s.get('strategy', '?')})_")
            for chunk in _send_chunks(lines):
                await message.channel.send(chunk)

        # ── !leaps [target|interval] ──────────────────────────────────────────
        elif cmd == "!leaps":
            from stonkslib.leaps.scanner import scan_leaps, get_vix_rank

            target_arg = None
            interval = "1wk"
            for p in parts[1:]:
                if p.lower() in VALID_INTERVALS:
                    interval = p.lower()
                else:
                    target_arg = p

            data = _load_tickers()
            if not target_arg or target_arg.lower() == "all":
                tickers = [t for items in data.values() for t in (items or [])]
                label = "all tickers"
            elif target_arg.lower() in data:
                tickers = data[target_arg.lower()] or []
                label = target_arg.lower()
            else:
                tickers = [target_arg.upper()]
                label = target_arg.upper()

            await message.channel.send(f"Scanning {len(tickers)} ticker(s) for LEAP opportunities (`{interval}`)...")

            loop = asyncio.get_event_loop()
            results, vix_current, vix_rank = await loop.run_in_executor(
                None, lambda: scan_leaps(tickers, interval)
            )

            if not results:
                vix_str = f"VIX {vix_current} ({vix_rank:.0f}% rank)" if vix_current else "VIX unavailable"
                await message.channel.send(f"No LEAP signals found. {vix_str}")
                return

            def _vix_label(r):
                if r is None:
                    return "unknown"
                return "LOW — good to buy" if r < 25 else "MODERATE" if r < 60 else "HIGH — options expensive"

            lines = [f"**LEAP Scan** — VIX {vix_current} | rank {vix_rank:.0f}% | {_vix_label(vix_rank)}"]

            calls = [r for r in results if r["direction"] == "CALL"]
            puts  = [r for r in results if r["direction"] == "PUT"]

            if calls:
                lines.append("\n**CALL candidates** (bullish)")
                for r in calls:
                    opt = r.get("option")
                    vix_note = " ⚠" if r["category"] == "stocks" else ""
                    opt_str = f"→ ${opt['strike']:.0f} exp {opt['expiry']}" if opt else ""
                    lines.append(
                        f"> `{r['ticker']}` ${r['current_price']:.2f} [{r['signal_count']} signals]{vix_note}"
                        f"  {r['top_reasons'][0] if r['top_reasons'] else ''}  {opt_str}"
                    )
            if puts:
                lines.append("\n**PUT candidates** (hedge/bearish)")
                for r in puts:
                    opt = r.get("option")
                    vix_note = " ⚠" if r["category"] == "stocks" else ""
                    opt_str = f"→ ${opt['strike']:.0f} exp {opt['expiry']}" if opt else ""
                    lines.append(
                        f"> `{r['ticker']}` ${r['current_price']:.2f} [{r['signal_count']} signals]{vix_note}"
                        f"  {r['top_reasons'][0] if r['top_reasons'] else ''}  {opt_str}"
                    )

            if calls or puts:
                lines.append("\n_⚠ = single stock, VIX is approximate_")

            for chunk in _send_chunks(lines):
                await message.channel.send(chunk)

        # ── !leaps-backtest [ticker] [interval] [call|put|auto] ───────────────
        elif cmd == "!leaps-backtest":
            from stonkslib.backtest.leaps import run_leaps_backtest
            from stonkslib.backtest.strategy import load_strategy

            ticker_arg = None
            interval = "1wk"
            option_type = "auto"
            for p in parts[1:]:
                if p.lower() in VALID_INTERVALS:
                    interval = p.lower()
                elif p.lower() in ("call", "put", "auto"):
                    option_type = p.lower()
                else:
                    ticker_arg = p.upper()

            if not ticker_arg:
                await message.channel.send("Usage: `!leaps-backtest AAPL` | `!leaps-backtest NVDA 1wk call`")
                return

            await message.channel.send(
                f"Running LEAP {option_type} backtest for `{ticker_arg}` (`{interval}`)..."
            )

            strategy_paths = list(STRATEGY_DIR.glob("*.yaml"))

            loop = asyncio.get_event_loop()

            def _run_leaps_backtests():
                results = []
                for path in strategy_paths:
                    active = _resolve_strategy(path, ticker=ticker_arg, option_type=option_type)
                    strat = load_strategy(active)
                    m = run_leaps_backtest(ticker_arg, interval, strat, option_type=option_type)
                    if m:
                        results.append(m)
                return results

            results = await loop.run_in_executor(None, _run_leaps_backtests)

            if not results:
                await message.channel.send(f"No LEAP backtest results for `{ticker_arg}`. Check that data exists.")
                return

            results.sort(key=lambda r: r["net_pnl"], reverse=True)
            lines = [f"**LEAP Backtest — {ticker_arg}** (`{interval}` · {option_type})"]
            lines.append(f"`{'#':<3} {'Strategy':<22} {'Type':<5} {'P&L':>10} {'Win%':>6} {'Avg%':>7} {'Trades':>7}`")
            for i, r in enumerate(results, 1):
                short = r["strategy"][:21] + "…" if len(r["strategy"]) > 22 else r["strategy"]
                marker = " ◀" if i == 1 else ""
                lines.append(
                    f"`{i:<3} {short:<22} {r['option_type'].upper():<5} "
                    f"${r['net_pnl']:>9.2f} {r['win_rate']:>5.1%} {r['avg_pnl_pct']:>6.1f}% "
                    f"{r['trades']:>7}`{marker}"
                )
            lines.append("_Priced via Black-Scholes + realized vol — approximate_")
            for chunk in _send_chunks(lines):
                await message.channel.send(chunk)

        # ── !leaps-trades TICKER [call|put] [strategy keyword] ───────────────
        elif cmd == "!leaps-trades":
            if len(parts) < 2:
                await message.channel.send(
                    "Usage: `!leaps-trades NVDA call` | `!leaps-trades NVDA call supertrend`"
                )
                return

            ticker_arg = parts[1].upper()
            option_type = "call"
            interval = "1wk"
            keyword_parts = []

            for p in parts[2:]:
                if p.lower() in VALID_INTERVALS:
                    interval = p.lower()
                elif p.lower() in ("call", "put", "auto"):
                    option_type = p.lower()
                else:
                    keyword_parts.append(p.lower())

            keyword = " ".join(keyword_parts) if keyword_parts else None

            from stonkslib.cli.leaps_trades import _find_csv
            import json as _json
            import pandas as _pd

            csv_path, candidates = _find_csv(ticker_arg, interval, option_type, keyword)

            if csv_path is None:
                if candidates is None:
                    await message.channel.send(
                        f"[!] No LEAP backtest data for `{ticker_arg}` (`{interval}`). "
                        f"Run `!leaps-backtest {ticker_arg}` first."
                    )
                elif candidates:
                    names = "  ".join(f"`{c.stem}`" for c in sorted(candidates))
                    await message.channel.send(f"[!] No match for `{keyword}`. Available: {names}")
                else:
                    await message.channel.send(f"[!] No LEAP trades for `{ticker_arg}` (`{interval}` · {option_type}).")
                return

            df = _pd.read_csv(csv_path)
            mf = csv_path.with_name(csv_path.stem + "_metrics.json")
            metrics = _json.loads(mf.read_text()) if mf.exists() else {}

            strategy_label = (csv_path.stem
                              .replace(f"_{option_type}", "")
                              .replace("_", " ").title())

            buys  = df[df["action"] == "BUY_LEAP"].reset_index(drop=True)
            sells = df[df["action"].isin(["SELL_LEAP", "SELL_LEAP_END"])].reset_index(drop=True)

            lines = [
                f"**LEAP Trades — {ticker_arg} · {option_type.upper()} · {strategy_label} · {interval}**"
            ]
            if metrics:
                lines.append(
                    f"Net P&L: **${metrics.get('net_pnl', 0):,.2f}** | "
                    f"Win rate: **{metrics.get('win_rate', 0):.1%}** | "
                    f"Avg trade: **{metrics.get('avg_pnl_pct', 0):.1f}%** | "
                    f"Trades: {metrics.get('trades', 0)}"
                )
            lines.append(f"`{'#':<3} {'Entry':<11} {'Spot':>7} {'K':>7} {'Prem':>6}  {'Exit':<11} {'P&L':>10} {'%':>7}  Reason`")

            for i in range(len(buys)):
                b = buys.iloc[i]
                entry = str(b["date"])[:10]
                spot_in = f"${b['spot']:.2f}"
                strike  = f"${b['strike']:.2f}"
                prem_in = f"${b['premium']:.2f}"

                if i < len(sells):
                    s = sells.iloc[i]
                    exit_d  = str(s["date"])[:10]
                    pnl     = s.get("pnl", 0)
                    pct     = s.get("pnl_pct", 0)
                    pnl_str = f"+${pnl:,.0f}" if pnl >= 0 else f"-${abs(pnl):,.0f}"
                    pct_str = f"+{pct:.0f}%" if pct >= 0 else f"{pct:.0f}%"
                    reason  = str(s.get("reason", ""))[:16]
                    mark    = "✓" if pnl >= 0 else "✗"
                    lines.append(
                        f"`{i+1:<3} {entry:<11} {spot_in:>7} {strike:>7} {prem_in:>6}  "
                        f"{exit_d:<11} {pnl_str:>10} {pct_str:>7}  {reason}` {mark}"
                    )
                else:
                    lines.append(
                        f"`{i+1:<3} {entry:<11} {spot_in:>7} {strike:>7} {prem_in:>6}  "
                        f"{'open':<11} {'—':>10} {'—':>7}  open`"
                    )

            for chunk in _send_chunks(lines):
                await message.channel.send(chunk)

        # ── !backtest [ticker] [interval] ─────────────────────────────────────
        elif cmd == "!backtest":
            from stonkslib.backtest.strategy import run_strategy_backtest, load_strategy

            ticker_arg = None
            interval = "1d"
            for p in parts[1:]:
                if p.lower() in VALID_INTERVALS:
                    interval = p.lower()
                else:
                    ticker_arg = p.upper()

            data = _load_tickers()
            all_tickers = [t for items in data.values() for t in (items or [])]
            tickers = [ticker_arg] if ticker_arg else all_tickers
            strategy_paths = list(STRATEGY_DIR.glob("*.yaml"))
            label = ticker_arg if ticker_arg else "all tickers"

            await message.channel.send(f"Running backtest for {label} (`{interval}`)...")

            loop = asyncio.get_event_loop()

            def _run_backtests():
                rows = []
                for path in strategy_paths:
                    metrics_list = []
                    for t in tickers:
                        active = _resolve_strategy(path, ticker=t)
                        strat = load_strategy(active)
                        m = run_strategy_backtest(t, interval, strat)
                        if m:
                            metrics_list.append(m)
                    if metrics_list:
                        avg_pnl = sum(m["net_pnl"] for m in metrics_list) / len(metrics_list)
                        avg_win = sum(m["win_rate"] for m in metrics_list) / len(metrics_list)
                        total_trades = sum(m["trades"] for m in metrics_list)
                        strat_name = load_strategy(path).get("name", path.stem)
                        rows.append((strat_name, avg_pnl, avg_win, total_trades))
                return rows

            results = await loop.run_in_executor(None, _run_backtests)

            if not results:
                await message.channel.send("No results — check that data exists for this interval.")
                return

            results.sort(key=lambda r: r[1], reverse=True)
            lines = [f"**Backtest — {label}** (`{interval}`)"]
            lines.append(f"`{'#':<3} {'Strategy':<22} {'Avg P&L':>10} {'Win%':>6} {'Trades':>7}`")
            for i, (name, pnl, win, trades) in enumerate(results, 1):
                short = name[:21] + "…" if len(name) > 22 else name
                marker = " ◀" if i == 1 else ""
                lines.append(f"`{i:<3} {short:<22} ${pnl:>9.2f} {win:>5.1%} {trades:>7}`{marker}")
            for chunk in _send_chunks(lines):
                await message.channel.send(chunk)

        # ── !trades TICKER [interval] [strategy keyword] ──────────────────────
        elif cmd == "!trades":
            if len(parts) < 2:
                await message.channel.send("Usage: `!trades AAPL rsi` | `!trades AAPL 1wk rsi only`")
                return

            ticker_arg = parts[1].upper()
            remaining = parts[2:]
            interval = "1d"
            keyword_parts = []
            for p in remaining:
                if p.lower() in VALID_INTERVALS:
                    interval = p.lower()
                else:
                    keyword_parts.append(p.lower())
            keyword = " ".join(keyword_parts)

            import re as _re
            import json as _json
            import pandas as _pd

            backtest_dir = PROJECT_ROOT / "data" / "backtest_results" / "strategy" / ticker_arg / interval
            if not backtest_dir.exists():
                await message.channel.send(
                    f"[!] No backtest data for `{ticker_arg}` (`{interval}`). Run `!backtest {ticker_arg}` first."
                )
                return

            csvs = sorted(backtest_dir.glob("*.csv"))
            if not csvs:
                await message.channel.send(f"[!] No trade logs for `{ticker_arg}` (`{interval}`).")
                return

            if keyword:
                slug_kw = _re.sub(r"[^a-z0-9]+", "_", keyword).strip("_")
                matched = [c for c in csvs if slug_kw in c.stem or keyword.replace(" ", "") in c.stem]
                if not matched:
                    matched = [c for c in csvs if any(w in c.stem for w in keyword_parts)]
            else:
                matched = csvs

            if not matched:
                names = "  ".join(f"`{c.stem}`" for c in csvs)
                await message.channel.send(f"[!] No match for `{keyword}`. Available: {names}")
                return

            if len(matched) > 1 and keyword:
                names = "  ".join(f"`{c.stem}`" for c in matched)
                await message.channel.send(f"Multiple matches — be more specific: {names}")
                return

            if len(matched) > 1:
                best, best_pnl = None, float("-inf")
                for c in matched:
                    mf = c.with_name(c.stem + "_metrics.json")
                    if mf.exists():
                        m = _json.loads(mf.read_text())
                        if m.get("net_pnl", float("-inf")) > best_pnl:
                            best_pnl, best = m["net_pnl"], c
                matched = [best] if best else [matched[0]]

            csv_path = matched[0]
            strategy_name = csv_path.stem.replace("_", " ").title()
            df = _pd.read_csv(csv_path)

            if df.empty:
                await message.channel.send(f"No trades recorded for `{csv_path.stem}`.")
                return

            buys  = df[df["action"] == "BUY"].reset_index(drop=True)
            sells = df[df["action"].isin(["SELL", "SELL_END"])].reset_index(drop=True)

            lines = [f"**Trade Log — {ticker_arg} · {strategy_name} · {interval}**"]
            lines.append(f"`{'#':<3} {'BUY date':<12} {'Price':>7}  {'SELL date':<12} {'Price':>7}  {'P&L':>9}`")
            for i in range(len(buys)):
                b = buys.iloc[i]
                buy_date  = str(b["date"])[:10]
                buy_price = f"${b['price']:.2f}"
                if i < len(sells):
                    s = sells.iloc[i]
                    sell_date  = str(s["date"])[:10]
                    sell_price = f"${s['price']:.2f}"
                    pnl = s.get("pnl", 0)
                    pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
                    marker = "✓" if pnl >= 0 else "✗"
                    lines.append(
                        f"`{i+1:<3} {buy_date:<12} {buy_price:>7}  {sell_date:<12} {sell_price:>7}  {pnl_str:>9}` {marker}"
                    )
                else:
                    lines.append(f"`{i+1:<3} {buy_date:<12} {buy_price:>7}  {'open':<12} {'—':>7}  {'—':>9}`")

            for chunk in _send_chunks(lines):
                await message.channel.send(chunk)

        # ── !optimize [ticker] [interval] [leaps [call|put]] ──────────────────
        elif cmd == "!optimize":
            ticker_arg = None
            interval = "1d"
            use_leaps = False
            option_type = "auto"

            for p in parts[1:]:
                if p.lower() in VALID_INTERVALS:
                    interval = p.lower()
                elif p.lower() == "leaps":
                    use_leaps = True
                elif p.lower() in ("call", "put", "auto"):
                    option_type = p.lower()
                else:
                    ticker_arg = p.upper()

            label = ticker_arg if ticker_arg else "all tickers"
            mode = f"LEAP {option_type}" if use_leaps else "equity"
            await message.channel.send(
                f"Optimizing {label} (`{interval}` · {mode}) — this takes a few minutes..."
            )

            from stonkslib.llm.optimizer import optimize
            from stonkslib.backtest.strategy import load_strategy

            data = _load_tickers()
            all_tickers = [t for items in data.values() for t in (items or [])]
            tickers = [ticker_arg] if ticker_arg else all_tickers
            strategy_paths = list(STRATEGY_DIR.glob("*.yaml"))

            loop = asyncio.get_event_loop()

            def _run_optimize():
                rows = []
                for path in strategy_paths:
                    strat_name = load_strategy(path).get("name", path.stem)
                    result = optimize(
                        strategy_path=path,
                        tickers=tickers,
                        interval=interval,
                        iterations=3,
                        output_ticker=ticker_arg,
                        use_leaps=use_leaps,
                        option_type=option_type,
                    )
                    if result and result.get("best_metrics"):
                        m = result["best_metrics"]
                        if use_leaps:
                            score = sum(x.get("avg_pnl_pct", 0) for x in m) / len(m)
                            rows.append((strat_name, score, None))
                        else:
                            avg_pnl = sum(x["net_pnl"] for x in m) / len(m)
                            avg_win = sum(x["win_rate"] for x in m) / len(m)
                            rows.append((strat_name, avg_pnl, avg_win))
                return rows

            results = await loop.run_in_executor(None, _run_optimize)

            if not results:
                await message.channel.send("Optimization failed — is Ollama running? (`ollama serve`)")
                return

            results.sort(key=lambda r: r[1], reverse=True)
            lines = [f"**Optimization — {label}** (`{interval}` · {mode})"]
            for i, row in enumerate(results, 1):
                name, score, win = row
                marker = " ◀ BEST" if i == 1 else ""
                if use_leaps:
                    lines.append(f"`{i}.` **{name}** — Avg trade return: {score:.1f}%{marker}")
                else:
                    lines.append(f"`{i}.` **{name}** — Avg P&L: ${score:.2f} | Win: {win:.1%}{marker}")
            for chunk in _send_chunks(lines):
                await message.channel.send(chunk)

    client.run(token)
