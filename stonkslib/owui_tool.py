"""
title: Stonks Watchlist & Signals
author: stanrey1011
description: Comprehensive stock analysis tool. Ask "how is AMD looking?" to get price, RSI, 52W range, 200MA, signals, earnings trend, backtest summary, and latest news sentiment in one call. Also supports watchlist management, signal scans, backtests, strategy optimization, trade logs, LEAP options analysis, and news fetching.
required_open_webui_version: 0.3.9
version: 1.4.0
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

    # --- snapshot & summary tools ---

    def get_ticker_summary(self, ticker: str, interval: str = "") -> str:
        """
        Get a comprehensive snapshot of a single ticker — use this to answer questions like
        "how is AMD looking?", "is NVDA a buy right now?", or "what's going on with TSLA?"

        Returns: current price and momentum, RSI, 52-week range position, distance from
        200-day MA, current BUY/SELL signals across all strategies, upcoming earnings date
        and EPS estimate, recent earnings beat/miss history, and best backtest result.

        ticker: symbol like AMD, NVDA, AAPL, BTC-USD
        interval: 1d (default) or 1wk
        """
        interval = interval or self.valves.default_interval
        ticker   = ticker.upper()

        import pandas as pd
        from datetime import datetime, timezone, date as date_type
        from pathlib import Path as _Path

        clean_dir     = PROJECT_ROOT / "data" / "ticker_data" / "clean"
        earnings_dir  = PROJECT_ROOT / "data" / "ticker_data" / "earnings"
        backtest_dir  = PROJECT_ROOT / "data" / "backtest_results" / "strategy"

        lines = [f"=== {ticker} snapshot ({interval}) ===", ""]

        # ── price & technicals ────────────────────────────────────────────────
        parquet = clean_dir / ticker / f"{interval}.parquet"
        if not parquet.exists():
            parquet = clean_dir / ticker / "1d.parquet"

        if parquet.exists():
            df = pd.read_parquet(parquet)
            df.columns = df.columns.str.title()
            df = df.sort_index()
            close = df["Close"]
            price = float(close.iloc[-1])

            day_chg = (price - float(close.iloc[-2])) / float(close.iloc[-2]) * 100 if len(close) >= 2 else None
            wk_chg  = (price - float(close.iloc[-6])) / float(close.iloc[-6]) * 100 if len(close) >= 6 else None

            w52   = close.tail(252)
            hi52  = float(w52.max())
            lo52  = float(w52.min())
            rng   = (price - lo52) / (hi52 - lo52) * 100 if hi52 != lo52 else 50.0
            p_lo  = (price - lo52)  / lo52  * 100
            p_hi  = (price - hi52)  / hi52  * 100

            ma200     = float(close.tail(200).mean()) if len(close) >= 200 else None
            pct_ma200 = (price - ma200) / ma200 * 100 if ma200 else None

            # RSI(14)
            delta = close.diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            last_loss = loss.iloc[-1]
            rsi = round(100 - 100 / (1 + gain.iloc[-1] / last_loss), 1) if last_loss and last_loss != 0 else None

            vol     = float(df["Volume"].iloc[-1])      if "Volume" in df.columns else None
            avg_vol = float(df["Volume"].tail(20).mean()) if "Volume" in df.columns and len(df) >= 20 else None
            vol_ratio = vol / avg_vol if vol and avg_vol else None

            # price line
            day_s = f"{'▲' if day_chg >= 0 else '▼'} {abs(day_chg):.2f}%" if day_chg is not None else "—"
            wk_s  = f"{'▲' if wk_chg  >= 0 else '▼'} {abs(wk_chg ):.2f}% (5d)" if wk_chg  is not None else ""
            vol_s = f"{vol/1e6:.1f}M ({vol_ratio:.1f}× avg)" if vol and vol_ratio else "—"
            lines.append(f"Price:   ${price:,.2f}  {day_s}  {wk_s}")
            lines.append(f"Volume:  {vol_s}")

            # short interest
            if not ticker.upper().endswith(("-USD", "-USDT")):
                try:
                    from stonkslib.utils.short_interest import get_short_interest
                    si = get_short_interest(ticker)
                    sp = si.get("short_pct")
                    dc = si.get("days_to_cover")
                    mc = si.get("mom_change")
                    if sp is not None:
                        si_note = " — HIGH (squeeze risk)" if sp >= 0.25 else \
                                  " — elevated" if sp >= 0.15 else \
                                  " — normal"
                        mom_s = f"  MoM: {'▲' if mc >= 0 else '▼'}{abs(mc):.1f}%" if mc is not None else ""
                        dc_s  = f"  |  {dc:.1f}d to cover" if dc is not None else ""
                        lines.append(f"Short:   {sp*100:.1f}% of float{si_note}{dc_s}{mom_s}")
                except Exception:
                    pass
            lines.append("")

            # RSI
            if rsi is not None:
                rsi_note = " — OVERSOLD (potential BUY zone)" if rsi <= 30 else \
                           " — OVERBOUGHT (extended)" if rsi >= 70 else \
                           " — neutral"
                lines.append(f"RSI(14): {rsi}{rsi_note}")

            # 52W
            rng_note = " — near 52W LOW (potential support/value)" if rng <= 20 else \
                       " — near 52W HIGH (extended)" if rng >= 80 else \
                       " — mid-range"
            lines.append(f"52W Range: {rng:.0f}% of range  [Lo ${lo52:,.2f} (+{p_lo:.1f}%) … Hi ${hi52:,.2f} ({p_hi:.1f}%)]  {rng_note}")

            # 200MA
            if pct_ma200 is not None:
                ma_note = " — above 200MA (bullish trend)" if pct_ma200 >= 0 else " — below 200MA (bearish trend)"
                lines.append(f"vs 200MA: {'+' if pct_ma200 >= 0 else ''}{pct_ma200:.1f}%{ma_note}")
            lines.append("")
        else:
            lines.append(f"No price data found for {ticker}. Run: stonks pipeline {ticker}")
            lines.append("")

        # ── signals ───────────────────────────────────────────────────────────
        signals = []
        try:
            signals = self._run_signals([ticker], interval)
            if signals:
                buys  = [s for s in signals if s["type"] == "BUY"]
                sells = [s for s in signals if s["type"] == "SELL"]
                lines.append(f"SIGNALS ({interval}):")
                for s in buys:
                    lines.append(f"  ▲ BUY  — {s['reason']}  [{s['strategy']}]")
                for s in sells:
                    lines.append(f"  ▼ SELL — {s['reason']}  [{s['strategy']}]")
                if not buys and not sells:
                    lines.append("  No signals on the latest bar.")
            else:
                lines.append(f"SIGNALS ({interval}): No signals on the latest bar.")
        except Exception as e:
            lines.append(f"SIGNALS: error — {e}")

        # squeeze flag: BUY signal + high short interest
        if signals and not ticker.upper().endswith(("-USD", "-USDT")):
            try:
                from stonkslib.utils.short_interest import get_short_interest
                si = get_short_interest(ticker)
                sp = si.get("short_pct")
                buys = [s for s in signals if s["type"] == "BUY"]
                if buys and sp and sp >= 0.15:
                    squeeze_level = "HIGH" if sp >= 0.25 else "MODERATE"
                    lines.append(f"  ⚡ SQUEEZE SETUP ({squeeze_level}): BUY signal + {sp*100:.1f}% short float — shorts may be forced to cover if this moves up")
            except Exception:
                pass
        lines.append("")

        # ── earnings ──────────────────────────────────────────────────────────
        earnings_path = earnings_dir / f"{ticker}.json"
        if earnings_path.exists():
            try:
                import json as _json
                with open(earnings_path) as f:
                    raw = _json.load(f)

                next_date = raw.get("next_date")
                next_eps  = raw.get("next_eps_estimate")
                history   = raw.get("history", [])

                lines.append("EARNINGS:")
                if next_date:
                    try:
                        nd   = date_type.fromisoformat(next_date[:10])
                        days = (nd - date_type.today()).days
                        days_s = f"{days} days" if days > 0 else "this week"
                        eps_s  = f" — EPS estimate: ${next_eps:.2f}" if next_eps else ""
                        lines.append(f"  Next: {nd.strftime('%b %-d, %Y')} ({days_s}){eps_s}")
                    except Exception:
                        lines.append(f"  Next: {next_date}")

                if history:
                    lines.append("  Recent quarters (date → reported vs estimate):")
                    beats = 0
                    for q in history[:5]:
                        d   = q.get("date", "?")[:10]
                        rep = q.get("reported_eps")
                        est = q.get("eps_estimate")
                        sur = q.get("surprise_pct")
                        if rep is not None and est is not None:
                            result = "Beat" if rep > est else "Miss"
                            if result == "Beat": beats += 1
                            sur_s = f"{sur:+.1f}%" if sur else ""
                            lines.append(f"    {d}: ${rep:.2f} vs ${est:.2f} est → {result} {sur_s}")
                        elif rep is not None:
                            lines.append(f"    {d}: EPS ${rep:.2f}")
                    total_with_est = sum(1 for q in history[:5] if q.get("reported_eps") is not None and q.get("eps_estimate") is not None)
                    if total_with_est > 0:
                        lines.append(f"  Beat rate: {beats}/{total_with_est} of last quarters with estimates")
            except Exception as e:
                lines.append(f"  Earnings data error: {e}")
        else:
            lines.append("EARNINGS: no cached data — run: stonks earnings-refresh")
        lines.append("")

        # ── best backtest ─────────────────────────────────────────────────────
        # ── news & sentiment ──────────────────────────────────────────────────
        try:
            from stonkslib.utils.news import get_news as _get_news
            news_data = _get_news(ticker, days=7)
            articles  = news_data.get("articles", [])
            sentiment = news_data.get("sentiment", {})

            bull = sentiment.get("bullish_pct")
            bear = sentiment.get("bearish_pct")
            buzz = sentiment.get("buzz")

            sent_parts = []
            if bull is not None:
                sent_parts.append(f"Bullish {bull*100:.0f}% / Bearish {bear*100:.0f}%")
            if buzz is not None:
                art_wk = sentiment.get("articles_week")
                wk_avg = sentiment.get("weekly_average")
                buzz_s = f"buzz {buzz:.2f}x"
                if art_wk and wk_avg and wk_avg > 0:
                    buzz_s += f" ({art_wk} articles vs {wk_avg:.0f} avg/wk)"
                sent_parts.append(buzz_s)

            if sent_parts or articles:
                lines.append("NEWS (last 7 days):")
                if sent_parts:
                    lines.append(f"  Sentiment: {' | '.join(sent_parts)}")
                for art in articles[:3]:
                    date_s   = art.get("date", "")
                    headline = art.get("headline", "")
                    source   = art.get("source", "")
                    lines.append(f"  [{date_s}] {headline}  -- {source}")
                if len(articles) > 3:
                    lines.append(f"  ... {len(articles) - 3} more articles (use get_news for full list)")
                lines.append("")
        except Exception as e:
            lines.append(f"NEWS: error -- {e}")
            lines.append("")

        bt_dir = backtest_dir / ticker / interval
        if bt_dir.exists():
            jsons = sorted(bt_dir.glob("*.json"))
            if jsons:
                import json as _json
                best = None
                for j in jsons:
                    try:
                        with open(j) as f:
                            m = _json.load(f)
                        if best is None or m.get("net_pnl", 0) > best.get("net_pnl", 0):
                            best = m
                    except Exception:
                        pass
                if best:
                    lines.append("BEST BACKTEST (historical):")
                    lines.append(
                        f"  {best.get('strategy','?')} — "
                        f"P&L ${best.get('net_pnl',0):,.2f} | "
                        f"Win rate {best.get('win_rate',0):.1%} | "
                        f"{best.get('trades',0)} trades"
                    )
                    lines.append("")

        return "\n".join(lines)

    def get_watchlist_summary(self) -> str:
        """
        Get a one-line technical snapshot for every ticker in the watchlist.
        Use this to compare tickers, find the most oversold, nearest to 52W lows,
        or cross-reference signals — e.g. "which of my stocks are oversold with earnings soon?"
        Returns price, day change, RSI, 52W position, signal, and next earnings for each ticker.
        """
        import pandas as pd
        from datetime import date as date_type
        import json as _json

        clean_dir    = PROJECT_ROOT / "data" / "ticker_data" / "clean"
        earnings_dir = PROJECT_ROOT / "data" / "ticker_data" / "earnings"

        wl = self._load()
        lines = ["Watchlist Summary:", ""]

        for cat, tickers in wl.items():
            if not tickers:
                continue
            lines.append(f"{cat.upper()}")
            lines.append(f"  {'Ticker':<10} {'Price':>8}  {'Chg%':>6}  {'RSI':>4}  {'52W%':>5}  {'Signal':<10}  Earnings")
            lines.append("  " + "-" * 72)

            for ticker in tickers:
                parquet = clean_dir / ticker / "1d.parquet"
                if not parquet.exists():
                    lines.append(f"  {ticker:<10} — no data")
                    continue
                try:
                    df    = pd.read_parquet(parquet)
                    df.columns = df.columns.str.title()
                    df    = df.sort_index()
                    close = df["Close"]
                    price = float(close.iloc[-1])
                    chg   = (price - float(close.iloc[-2])) / float(close.iloc[-2]) * 100 if len(close) >= 2 else None

                    w52   = close.tail(252)
                    hi52, lo52 = float(w52.max()), float(w52.min())
                    rng   = (price - lo52) / (hi52 - lo52) * 100 if hi52 != lo52 else None

                    delta = close.diff()
                    gain  = delta.clip(lower=0).rolling(14).mean()
                    loss  = (-delta.clip(upper=0)).rolling(14).mean()
                    ll    = loss.iloc[-1]
                    rsi   = round(100 - 100 / (1 + gain.iloc[-1] / ll), 0) if ll and ll != 0 else None
                except Exception:
                    lines.append(f"  {ticker:<10} — read error")
                    continue

                # signal from last alert cache
                alert_cache = PROJECT_ROOT / "data" / "last_alert.json"
                signal = "—"
                if alert_cache.exists():
                    try:
                        with open(alert_cache) as f:
                            ac = _json.load(f)
                        sigs = ac.get("results", {}).get(ticker, {}).get("signals", [])
                        types = {s["type"] for s in sigs}
                        signal = "▲ BUY" if types == {"BUY"} else "▼ SELL" if types == {"SELL"} else "⚡ Mixed" if types else "—"
                    except Exception:
                        pass

                # earnings
                ep = earnings_dir / f"{ticker}.json"
                earnings_s = "—"
                if ep.exists():
                    try:
                        with open(ep) as f:
                            er = _json.load(f)
                        nd = er.get("next_date")
                        if nd:
                            d    = date_type.fromisoformat(nd[:10])
                            days = (d - date_type.today()).days
                            if days >= 0:
                                earnings_s = f"{d.strftime('%b %-d')} ({days}d)"
                    except Exception:
                        pass

                chg_s = f"{'▲' if chg >= 0 else '▼'}{abs(chg):.1f}%" if chg is not None else "  —  "
                rsi_s = f"{rsi:.0f}" if rsi is not None else "—"
                rng_s = f"{rng:.0f}%" if rng is not None else "—"
                lines.append(
                    f"  {ticker:<10} ${price:>7,.2f}  {chg_s:>6}  {rsi_s:>4}  {rng_s:>5}  {signal:<10}  {earnings_s}"
                )
            lines.append("")

        return "\n".join(lines)

    def get_last_alerts(self) -> str:
        """
        Return the results of the most recent alert scan without re-running it.
        Shows which tickers had BUY or SELL signals and the reasons, along with
        when the scan was run and which interval was used.
        Much faster than scan_watchlist — use this when you just want to see what fired last time.
        """
        import json as _json
        alert_cache = PROJECT_ROOT / "data" / "last_alert.json"
        if not alert_cache.exists():
            return "No cached alerts found. Run scan_watchlist or trigger an alert scan from the Alerts page."

        try:
            with open(alert_cache) as f:
                data = _json.load(f)
        except Exception as e:
            return f"Could not read alert cache: {e}"

        ts       = data.get("ts", "unknown time")
        interval = data.get("interval", "?")
        results  = data.get("results", {})

        lines = [f"Last Alert Scan — {interval} — run at {ts}", ""]

        buys = []
        sells = []
        mixed = []
        for ticker, info in results.items():
            sigs  = info.get("signals", [])
            types = {s["type"] for s in sigs}
            if types == {"BUY"}:
                buys.append((ticker, sigs))
            elif types == {"SELL"}:
                sells.append((ticker, sigs))
            elif types:
                mixed.append((ticker, sigs))

        if buys:
            lines.append("▲ BUY SIGNALS:")
            for ticker, sigs in buys:
                reasons = " | ".join(f"{s['reason']} ({s.get('strategy','')})" for s in sigs)
                lines.append(f"  {ticker}: {reasons}")
            lines.append("")

        if sells:
            lines.append("▼ SELL SIGNALS:")
            for ticker, sigs in sells:
                reasons = " | ".join(f"{s['reason']} ({s.get('strategy','')})" for s in sigs)
                lines.append(f"  {ticker}: {reasons}")
            lines.append("")

        if mixed:
            lines.append("⚡ MIXED SIGNALS:")
            for ticker, sigs in mixed:
                buy_r  = [s['reason'] for s in sigs if s['type'] == 'BUY']
                sell_r = [s['reason'] for s in sigs if s['type'] == 'SELL']
                lines.append(f"  {ticker}: BUY({', '.join(buy_r)}) / SELL({', '.join(sell_r)})")
            lines.append("")

        if not buys and not sells and not mixed:
            lines.append("No signals fired in the last scan.")

        return "\n".join(lines)

    def get_news(self, ticker: str, days: int = 7) -> str:
        """
        Get recent news headlines and sentiment for a ticker.
        Use this when the user asks about news, what's in the press, or what's driving a stock.
        ticker: symbol like AAPL or AMD
        days: how many days back to fetch (default 7, max 30)
        Returns sentiment (bullish%, bearish%, buzz ratio) and all recent headlines with summaries.
        Requires FINNHUB_API_KEY in .env.
        """
        ticker = ticker.upper()
        days   = max(1, min(days, 30))

        try:
            from stonkslib.utils.news import get_news as _get_news
            data = _get_news(ticker, days=days)
        except Exception as e:
            return f"Error fetching news for {ticker}: {e}"

        articles  = data.get("articles", [])
        sentiment = data.get("sentiment", {})
        fetched   = data.get("fetched_at", "")

        lines = [f"=== {ticker} News (last {days} days) ===", ""]

        bull = sentiment.get("bullish_pct")
        bear = sentiment.get("bearish_pct")
        buzz = sentiment.get("buzz")
        art_wk = sentiment.get("articles_week")
        wk_avg = sentiment.get("weekly_average")

        if bull is not None or buzz is not None:
            lines.append("SENTIMENT:")
            if bull is not None:
                tone = "Bullish" if bull > 0.55 else "Bearish" if bull < 0.45 else "Neutral"
                lines.append(f"  {tone} — {bull*100:.0f}% bullish / {bear*100:.0f}% bearish")
            if buzz is not None:
                buzz_note = " (above average activity)" if buzz > 1.2 else \
                            " (below average activity)" if buzz < 0.8 else " (normal activity)"
                art_s = f" | {art_wk} articles this week vs {wk_avg:.0f} avg" if art_wk and wk_avg else ""
                lines.append(f"  Buzz: {buzz:.2f}x{buzz_note}{art_s}")
            lines.append("")

        if not articles:
            lines.append(f"No articles found for {ticker} in the last {days} days.")
            return "\n".join(lines)

        lines.append(f"HEADLINES ({len(articles)} articles):")
        for art in articles:
            date_s   = art.get("date", "")
            headline = art.get("headline", "")
            source   = art.get("source", "")
            summary  = art.get("summary", "")
            url      = art.get("url", "")
            lines.append(f"\n  [{date_s}] {headline}")
            lines.append(f"  Source: {source}")
            if summary and summary != headline:
                # truncate long summaries
                s = summary[:300] + "..." if len(summary) > 300 else summary
                lines.append(f"  {s}")
            if url:
                lines.append(f"  URL: {url}")

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
