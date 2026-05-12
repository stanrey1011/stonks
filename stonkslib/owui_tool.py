"""
title: Stonks Watchlist & Signals
author: stanrey1011
description: Manage your stonks watchlist, scan for signals, run backtests, optimize strategies, view trade logs, and scan/backtest LEAP options. Shares tickers.yaml with the CLI and Discord bot.
required_open_webui_version: 0.3.9
version: 1.2.0
licence: MIT
"""

import glob
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml
from pydantic import BaseModel

PROJECT_ROOT = Path("/home/as/stonks")
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
STRATEGY_DIR = PROJECT_ROOT / "stonkslib" / "strategies"
BACKTEST_DIR = PROJECT_ROOT / "data" / "backtest_results" / "strategy"
LEAPS_DIR = PROJECT_ROOT / "data" / "backtest_results" / "leaps"
STONKS_BIN = PROJECT_ROOT / "venv" / "bin" / "stonks"

# Make stonkslib importable from within Open WebUI's process
sys.path.insert(0, str(PROJECT_ROOT))
_sp = glob.glob(str(PROJECT_ROOT / "venv/lib/python*/site-packages"))
if _sp:
    sys.path.insert(0, _sp[0])

VALID_CATEGORIES = ("stocks", "crypto", "etfs")


def _resolve_strategy_path(path: Path, ticker: str = None, option_type: str = None) -> Path:
    """Tiered YAML fallback: LEAP-specific → ticker-specific → global optimized → base."""
    opt_dir = STRATEGY_DIR / "optimized"
    if ticker and option_type:
        leap_opt = opt_dir / f"{path.stem}_{ticker}_leaps_{option_type}_optimized.yaml"
        if leap_opt.exists():
            return leap_opt
    if ticker:
        ticker_opt = opt_dir / f"{path.stem}_{ticker}_optimized.yaml"
        if ticker_opt.exists():
            return ticker_opt
    global_opt = opt_dir / f"{path.stem}_optimized.yaml"
    if global_opt.exists():
        return global_opt
    return path


class Tools:
    class Valves(BaseModel):
        default_interval: str = "1d"

    def __init__(self):
        self.valves = self.Valves()

    # --- helpers ---

    def _load(self) -> dict:
        with open(TICKER_YAML) as f:
            return yaml.safe_load(f) or {}

    def _save(self, data: dict):
        with open(TICKER_YAML, "w") as f:
            yaml.dump(data, f, default_flow_style=False)

    def _fmt_watchlist(self, data: dict) -> str:
        lines = []
        for cat, items in data.items():
            if items:
                lines.append(f"{cat.capitalize()}: {', '.join(items)}")
        return "\n".join(lines) if lines else "Watchlist is empty."

    def _run_signals(self, tickers: list[str], interval: str) -> list[dict]:
        from stonkslib.alerts.signals import check_signals

        strategy_paths = list(STRATEGY_DIR.glob("*.yaml"))
        results = []
        for path in strategy_paths:
            for ticker in tickers:
                active = _resolve_strategy_path(path, ticker)
                with open(active) as f:
                    strat = yaml.safe_load(f)
                signals = check_signals(ticker, interval, strat)
                if signals:
                    for s in signals:
                        s["strategy"] = strat.get("name", path.stem)
                    results.extend(signals)
        return results

    def _fmt_signals(self, signals: list[dict], label: str, interval: str) -> str:
        if not signals:
            return f"No signals for {label} on {interval}."
        buys = [s for s in signals if s["type"] == "BUY"]
        sells = [s for s in signals if s["type"] == "SELL"]
        lines = [f"Signals — {label} ({interval}):"]
        if buys:
            lines.append("BUY:")
            for s in buys:
                lines.append(f"  {s['ticker']} ${s['close']:.2f} — {s['reason']} ({s['strategy']})")
        if sells:
            lines.append("SELL:")
            for s in sells:
                lines.append(f"  {s['ticker']} ${s['close']:.2f} — {s['reason']} ({s['strategy']})")
        return "\n".join(lines)

    # --- standard tools ---

    def get_watchlist(self) -> str:
        """Get the current ticker watchlist grouped by category."""
        return self._fmt_watchlist(self._load())

    def add_ticker(self, ticker: str, category: str) -> str:
        """
        Add a ticker to the watchlist and fetch its data.
        ticker: symbol like AAPL or BTC-USD
        category: stocks, crypto, or etfs
        After adding, the pipeline runs automatically (fetch → clean → analyze).
        """
        ticker = ticker.upper()
        category = category.lower()
        if category not in VALID_CATEGORIES:
            return f"Unknown category '{category}'. Use: stocks, crypto, or etfs."

        data = self._load()
        data.setdefault(category, [])
        if ticker in data[category]:
            return f"{ticker} is already in {category}."

        data[category].append(ticker)
        self._save(data)

        result = subprocess.run(
            [str(STONKS_BIN), "pipeline", ticker],
            capture_output=True, text=True, timeout=180,
        )

        if result.returncode == 0:
            return f"Added {ticker} to {category} and fetched data.\n\n{self._fmt_watchlist(data)}"
        else:
            err = result.stderr.strip() or "unknown error"
            return (
                f"Added {ticker} to {category}, but the pipeline failed: {err}\n"
                f"Run manually: stonks pipeline {ticker}\n\n{self._fmt_watchlist(data)}"
            )

    def remove_ticker(self, ticker: str) -> str:
        """Remove a ticker from the watchlist."""
        ticker = ticker.upper()
        data = self._load()
        removed_from = None
        for cat, items in data.items():
            if items and ticker in items:
                items.remove(ticker)
                removed_from = cat
                break
        if not removed_from:
            return f"{ticker} not found in watchlist."
        self._save(data)
        return f"Removed {ticker} from {removed_from}.\n\n{self._fmt_watchlist(data)}"

    def scan_ticker(self, ticker: str, interval: str = "") -> str:
        """
        Scan a single ticker for BUY/SELL signals across all active strategies.
        ticker: symbol like AAPL
        interval: 1d (default) or 1wk for weekly signals
        Uses per-ticker optimized strategy parameters automatically when available.
        """
        interval = interval or self.valves.default_interval
        ticker = ticker.upper()
        try:
            signals = self._run_signals([ticker], interval)
        except Exception as e:
            return f"Error scanning {ticker}: {e}"
        return self._fmt_signals(signals, ticker, interval)

    def scan_watchlist(self, interval: str = "") -> str:
        """
        Scan all tickers in the watchlist for signals across all active strategies.
        interval: 1d (default) or 1wk for weekly signals
        Uses per-ticker optimized strategy parameters automatically when available.
        """
        interval = interval or self.valves.default_interval
        data = self._load()
        all_tickers = [t for items in data.values() for t in (items or [])]
        if not all_tickers:
            return "Watchlist is empty."
        try:
            signals = self._run_signals(all_tickers, interval)
        except Exception as e:
            return f"Error scanning watchlist: {e}"
        return self._fmt_signals(signals, f"{len(all_tickers)} tickers", interval)

    def backtest_ticker(self, ticker: str, interval: str = "") -> str:
        """
        Run a backtest for a ticker across all strategies and return a ranked summary.
        ticker: symbol like AAPL
        interval: 1d (default) or 1wk
        Results are saved to disk so get_trades can be called afterwards.
        """
        interval = interval or self.valves.default_interval
        ticker = ticker.upper()

        from stonkslib.backtest.strategy import run_strategy_backtest, load_strategy

        strategy_paths = list(STRATEGY_DIR.glob("*.yaml"))
        results = []
        for path in strategy_paths:
            active = _resolve_strategy_path(path, ticker)
            strat = load_strategy(active)
            m = run_strategy_backtest(ticker, interval, strat)
            if m:
                results.append(m)

        if not results:
            return f"No backtest results for {ticker} ({interval}). Make sure data exists — try add_ticker first."

        results.sort(key=lambda r: r["net_pnl"], reverse=True)
        lines = [f"Backtest Results — {ticker} ({interval}):"]
        lines.append(f"{'#':<3} {'Strategy':<22} {'P&L':>10} {'Win%':>6} {'Trades':>7}")
        lines.append("-" * 52)
        for i, m in enumerate(results, 1):
            marker = " ◀ BEST" if i == 1 else ""
            name = m["strategy"][:21] + "…" if len(m["strategy"]) > 22 else m["strategy"]
            lines.append(f"{i:<3} {name:<22} ${m['net_pnl']:>9.2f} {m['win_rate']:>5.1%} {m['trades']:>7}{marker}")
        return "\n".join(lines)

    def optimize_ticker(self, ticker: str, interval: str = "", iterations: int = 3) -> str:
        """
        Optimize all strategy parameters for a ticker using the local LLM (Ollama).
        ticker: symbol like AAPL
        interval: 1d (default) or 1wk
        iterations: number of optimization rounds (default 3, max 5)
        Saves per-ticker optimized YAMLs used automatically by future scans and backtests.
        """
        interval = interval or self.valves.default_interval
        ticker = ticker.upper()
        iterations = min(iterations, 5)

        from stonkslib.llm.optimizer import optimize

        strategy_paths = list(STRATEGY_DIR.glob("*.yaml"))
        results = []
        for path in strategy_paths:
            result = optimize(
                strategy_path=path, tickers=[ticker], interval=interval,
                iterations=iterations, output_ticker=ticker,
            )
            if result and result.get("best_metrics"):
                m = result["best_metrics"]
                avg_pnl = sum(x["net_pnl"] for x in m) / len(m)
                avg_win = sum(x["win_rate"] for x in m) / len(m)
                strat_name = result["best_strategy"].get("name", path.stem)
                results.append((strat_name, avg_pnl, avg_win))

        if not results:
            return "Optimization failed — is Ollama running? Start with: ollama serve"

        results.sort(key=lambda r: r[1], reverse=True)
        lines = [f"Optimization complete — {ticker} ({interval}):"]
        for i, (name, pnl, win) in enumerate(results, 1):
            marker = " ◀ BEST" if i == 1 else ""
            lines.append(f"{i}. {name} — P&L: ${pnl:.2f} | Win: {win:.1%}{marker}")
        lines.append("\nPer-ticker optimized params saved. Run backtest_ticker to see updated results.")
        return "\n".join(lines)

    def get_trades(self, ticker: str, strategy: str, interval: str = "") -> str:
        """
        Show the buy/sell trade log for a specific strategy so you can look up entries on a chart.
        ticker: symbol like AAPL
        strategy: partial strategy name, e.g. 'rsi only', 'supertrend', 'macd', 'bollinger'
        interval: 1d (default) or 1wk
        Run backtest_ticker first if no data exists yet.
        """
        interval = interval or self.valves.default_interval
        ticker = ticker.upper()

        backtest_path = BACKTEST_DIR / ticker / interval
        if not backtest_path.exists():
            return f"No backtest data for {ticker} ({interval}). Run backtest_ticker first."

        csvs = sorted(backtest_path.glob("*.csv"))
        if not csvs:
            return f"No trade logs found for {ticker} ({interval}). Run backtest_ticker first."

        slug_kw = re.sub(r"[^a-z0-9]+", "_", strategy.lower()).strip("_")
        words = [w for w in re.split(r"[^a-z0-9]+", strategy.lower()) if w]
        matched = [c for c in csvs if slug_kw in c.stem]
        if not matched:
            matched = [c for c in csvs if all(w in c.stem for w in words)]
        if not matched:
            matched = [c for c in csvs if any(w in c.stem for w in words)]

        if not matched:
            available = ", ".join(c.stem for c in csvs)
            return f"No match for '{strategy}'. Available: {available}"

        if len(matched) > 1:
            available = ", ".join(c.stem for c in matched)
            return f"Multiple matches for '{strategy}' — be more specific: {available}"

        import pandas as pd
        csv_path = matched[0]
        strategy_name = csv_path.stem.replace("_", " ").title()
        df = pd.read_csv(csv_path)

        if df.empty:
            return f"No trades recorded for {strategy_name}."

        buys = df[df["action"] == "BUY"].reset_index(drop=True)
        sells = df[df["action"].isin(["SELL", "SELL_END"])].reset_index(drop=True)

        lines = [f"Trade Log — {ticker} · {strategy_name} · {interval}"]
        lines.append(f"{'#':<3} {'BUY date':<12} {'Price':>7}   {'SELL date':<12} {'Price':>7}   {'P&L':>9}")
        lines.append("-" * 60)

        for i in range(len(buys)):
            b = buys.iloc[i]
            buy_date = str(b["date"])[:10]
            buy_price = f"${b['price']:.2f}"
            if i < len(sells):
                s = sells.iloc[i]
                sell_date = str(s["date"])[:10]
                sell_price = f"${s['price']:.2f}"
                pnl = float(s.get("pnl", 0))
                pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
                win = "✓" if pnl >= 0 else "✗"
                lines.append(f"{i+1:<3} {buy_date:<12} {buy_price:>7}   {sell_date:<12} {sell_price:>7}   {pnl_str:>9} {win}")
            else:
                lines.append(f"{i+1:<3} {buy_date:<12} {buy_price:>7}   {'open':<12} {'—':>7}   {'—':>9}")

        total_pnl = sells["pnl"].sum() if "pnl" in sells.columns else 0
        lines.append("-" * 60)
        lines.append(f"Total P&L: ${total_pnl:.2f}  |  {len(buys)} trades")
        return "\n".join(lines)

    # --- LEAP tools ---

    def scan_leaps(self, interval: str = "1wk") -> str:
        """
        Scan all watchlist tickers for LEAP call/put buying opportunities.
        Shows VIX rank (IV proxy), signal counts across strategies, and live option chain data.
        interval: 1wk (default) or 1d
        Returns ranked candidates with strike, premium, expiry, and direction.
        """
        data = self._load()
        all_tickers = [t for items in data.values() for t in (items or [])]
        if not all_tickers:
            return "Watchlist is empty."

        try:
            from stonkslib.leaps.scanner import scan_leaps as _scan
            candidates = _scan(all_tickers, interval=interval)
        except Exception as e:
            return f"LEAP scan error: {e}"

        if not candidates:
            return "No LEAP candidates found. Check that 1wk data exists (run: stonks pipeline)."

        try:
            from stonkslib.leaps.scanner import get_vix_rank
            vix_val, vix_rank = get_vix_rank()
            vix_label = "LOW" if vix_rank < 0.33 else "HIGH" if vix_rank > 0.66 else "MODERATE"
            header = f"VIX: {vix_val:.1f} ({vix_rank:.0%} rank — {vix_label} IV environment)"
        except Exception:
            header = "VIX data unavailable"

        lines = [f"LEAP Scan — {len(all_tickers)} tickers ({interval})", header, ""]
        lines.append(f"{'#':<3} {'Ticker':<7} {'Dir':<5} {'Score':>5}  {'Strike':>7}  {'Prem':>7}  {'Expiry':<12}  IV%")
        lines.append("-" * 65)
        for i, c in enumerate(candidates[:20], 1):
            direction = c.get("direction", "?").upper()
            score = c.get("score", 0)
            strike = f"${c['strike']:.2f}" if c.get("strike") else "—"
            prem = f"${c['premium']:.2f}" if c.get("premium") else "—"
            expiry = c.get("expiry", "—")
            iv = f"{c['iv']:.0%}" if c.get("iv") else "—"
            lines.append(f"{i:<3} {c['ticker']:<7} {direction:<5} {score:>5}  {strike:>7}  {prem:>7}  {expiry:<12}  {iv}")
        return "\n".join(lines)

    def leaps_backtest(self, ticker: str, option_type: str = "call", interval: str = "1wk") -> str:
        """
        Run a LEAP options backtest for a ticker using Black-Scholes pricing.
        ticker: symbol like NVDA
        option_type: call, put, or auto (picks best direction per signal)
        interval: 1wk (default) or 1d
        Exits are stop-loss (50% premium loss) or expiry only — no signal-based exits.
        Results are saved so get_leaps_trades can show the trade log.
        """
        ticker = ticker.upper()
        option_type = option_type.lower()
        if option_type not in ("call", "put", "auto"):
            return "option_type must be call, put, or auto."

        try:
            from stonkslib.backtest.leaps import run_leaps_backtest
            from stonkslib.backtest.strategy import load_strategy

            strategy_paths = list(STRATEGY_DIR.glob("*.yaml"))
            results = []
            for path in strategy_paths:
                active = _resolve_strategy_path(path, ticker, option_type)
                strat = load_strategy(active)
                m = run_leaps_backtest(
                    ticker=ticker, interval=interval, strategy=strat,
                    option_type=option_type,
                )
                if m:
                    results.append(m)
        except Exception as e:
            return f"LEAP backtest error for {ticker}: {e}"

        if not results:
            return f"No LEAP backtest results for {ticker}. Make sure {interval} data exists."

        results.sort(key=lambda r: r.get("avg_pnl_pct", 0), reverse=True)
        lines = [f"LEAP Backtest — {ticker} ({option_type.upper()}, {interval}):"]
        lines.append(f"{'#':<3} {'Strategy':<22} {'Net P&L':>10} {'Avg%':>7} {'Win%':>6} {'Trades':>7}")
        lines.append("-" * 60)
        for i, m in enumerate(results, 1):
            marker = " ◀ BEST" if i == 1 else ""
            name = m.get("strategy", "?")
            name = name[:21] + "…" if len(name) > 22 else name
            lines.append(
                f"{i:<3} {name:<22} ${m.get('net_pnl', 0):>9.2f} "
                f"{m.get('avg_pnl_pct', 0):>6.1f}% {m.get('win_rate', 0):>5.1%} "
                f"{m.get('trades', 0):>7}{marker}"
            )
        lines.append("\nRun get_leaps_trades to see entry/exit dates.")
        return "\n".join(lines)

    def get_leaps_trades(self, ticker: str, option_type: str = "call", strategy: str = "") -> str:
        """
        Show the LEAP entry/exit trade log for a ticker so you can verify entries on a chart.
        ticker: symbol like NVDA
        option_type: call or put
        strategy: partial strategy name to match (e.g. 'supertrend', 'rsi macd'). Leave blank for best by avg trade %.
        Run leaps_backtest first if no data exists.
        """
        ticker = ticker.upper()
        option_type = option_type.lower()

        try:
            from stonkslib.cli.leaps_trades import print_leaps_trades
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                found = print_leaps_trades(
                    ticker=ticker, interval="1wk",
                    option_type=option_type, keyword=strategy or None,
                )
            output = buf.getvalue().strip()
        except Exception as e:
            return f"Error loading LEAP trades for {ticker}: {e}"

        if not output:
            return f"No LEAP trade data for {ticker} ({option_type}). Run leaps_backtest first."
        return output

    def optimize_leaps(self, ticker: str, option_type: str = "call", interval: str = "1wk", iterations: int = 3) -> str:
        """
        Optimize strategy parameters specifically for LEAP options on a ticker using the local LLM.
        ticker: symbol like NVDA
        option_type: call, put, or auto
        interval: 1wk (default) or 1d
        iterations: optimization rounds (default 3, max 5)
        Scores strategies by avg trade % return (not raw P&L) to avoid premium-size bias.
        Saves LEAP-specific optimized YAMLs used automatically by leaps_backtest.
        """
        ticker = ticker.upper()
        option_type = option_type.lower()
        if option_type not in ("call", "put", "auto"):
            return "option_type must be call, put, or auto."
        iterations = min(iterations, 5)

        try:
            from stonkslib.llm.optimizer import optimize

            strategy_paths = list(STRATEGY_DIR.glob("*.yaml"))
            results = []
            for path in strategy_paths:
                result = optimize(
                    strategy_path=path, tickers=[ticker], interval=interval,
                    iterations=iterations, output_ticker=ticker,
                    use_leaps=True, option_type=option_type,
                )
                if result and result.get("best_metrics"):
                    m = result["best_metrics"]
                    avg_pct = sum(x.get("avg_pnl_pct", 0) for x in m) / len(m)
                    strat_name = result["best_strategy"].get("name", path.stem)
                    results.append((strat_name, avg_pct))
        except Exception as e:
            return f"LEAP optimization error: {e}"

        if not results:
            return "Optimization failed — is Ollama running? Start with: ollama serve"

        results.sort(key=lambda r: r[1], reverse=True)
        lines = [f"LEAP Optimization complete — {ticker} ({option_type.upper()}, {interval}):"]
        for i, (name, avg_pct) in enumerate(results, 1):
            marker = " ◀ BEST" if i == 1 else ""
            lines.append(f"{i}. {name} — Avg trade: {avg_pct:.1f}%{marker}")
        lines.append("\nLEAP-specific params saved. Run leaps_backtest to see updated results.")
        return "\n".join(lines)
