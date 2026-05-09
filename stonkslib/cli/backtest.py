import click
import yaml
from pathlib import Path
from stonkslib.utils.logging import setup_logging

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = PROJECT_ROOT / "stonkslib" / "strategies"
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
logger = setup_logging(PROJECT_ROOT / "log", "backtest.log")


def _resolve_tickers(target):
    with open(TICKER_YAML) as f:
        data = yaml.safe_load(f) or {}
    if not target or target.lower() == "all":
        return [t for items in data.values() for t in (items or [])]
    for cat, tickers in data.items():
        if cat.lower() == target.lower():
            return tickers or []
    return [target.upper()]


def _load_strategies(all_strategies, strategy):
    if all_strategies:
        return list(STRATEGY_DIR.glob("*.yaml"))
    return [STRATEGY_DIR / strategy]


@click.command()
@click.argument("target", required=False, default=None,
                metavar="[TICKER|CATEGORY|all]")
@click.option("--strategy", default=None,
              help="Strategy YAML filename (e.g. rsi.yaml). Omit for --all-strategies.")
@click.option("--all-strategies", "all_strategies", is_flag=True,
              help="Run all strategy YAMLs")
@click.option("--interval",
              type=click.Choice(["1m", "5m", "15m", "30m", "1h", "1d", "1wk"]),
              default="1d", show_default=True)
def backtest(target, strategy, all_strategies, interval):
    """Run strategy backtests.

    TARGET can be a ticker (AAPL), a category (stocks/etfs/crypto), or 'all'.\n

    Examples:\n
      stonks backtest AAPL --strategy rsi.yaml --interval 1d\n
      stonks backtest stocks --all-strategies\n
      stonks backtest all --all-strategies --interval 1wk
    """
    from stonkslib.backtest.strategy import run_strategy_backtest, load_strategy

    if not target:
        print("[!] Provide a ticker (AAPL), category (stocks/etfs/crypto), or 'all'")
        return
    if not strategy and not all_strategies:
        print("[!] Provide --strategy <file> or --all-strategies")
        return

    tickers = _resolve_tickers(target)
    strategy_paths = _load_strategies(all_strategies, strategy)

    missing = [p for p in strategy_paths if not p.exists()]
    if missing:
        for p in missing:
            print(f"[!] Strategy not found: {p}")
        return

    results = []
    for path in strategy_paths:
        strat = load_strategy(path)
        strat_name = strat.get("name", path.stem)
        metrics_list = []
        for t in tickers:
            m = run_strategy_backtest(t, interval, strat)
            if m:
                metrics_list.append(m)
        if metrics_list:
            avg_pnl = sum(m["net_pnl"] for m in metrics_list) / len(metrics_list)
            avg_win = sum(m["win_rate"] for m in metrics_list) / len(metrics_list)
            total_trades = sum(m["trades"] for m in metrics_list)
            results.append((strat_name, avg_pnl, avg_win, total_trades))

    if not results:
        print("[!] No results — check data exists for this interval")
        return

    results.sort(key=lambda r: r[1], reverse=True)
    label = target if target.lower() in ("all",) else target
    print(f"\n{'='*60}")
    print(f"  Backtest Results — {label} ({interval})")
    print(f"{'='*60}")
    print(f"  {'#':<3} {'Strategy':<24} {'Avg P&L':>10} {'Win%':>7} {'Trades':>7}")
    print(f"  {'-'*55}")
    for i, (name, pnl, win, trades) in enumerate(results, 1):
        short = name[:23] + "…" if len(name) > 24 else name
        marker = "  ◀ BEST" if i == 1 else ""
        print(f"  {i:<3} {short:<24} ${pnl:>9.2f} {win:>6.1%} {trades:>7}{marker}")
    print(f"{'='*60}\n")
