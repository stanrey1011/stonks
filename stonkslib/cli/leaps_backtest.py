import click
import yaml
from pathlib import Path
from stonkslib.utils.logging import setup_logging

from stonkslib.utils.active_strategies import resolve_strategy_set

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = PROJECT_ROOT / "stonkslib" / "strategies"
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
logger = setup_logging(PROJECT_ROOT / "log", "leaps.log")


def _resolve_tickers(target):
    with open(TICKER_YAML) as f:
        data = yaml.safe_load(f) or {}
    if not target or target.lower() == "all":
        return [t for items in data.values() for t in (items or [])
                if not any(c in t for c in ["-USD"])]  # skip crypto — no options
    for cat, tickers in data.items():
        if cat.lower() == target.lower():
            return tickers or []
    return [target.upper()]


def _resolve_strategy_path(path, ticker=None, option_type="auto"):
    """Prefer LEAP-specific → ticker-specific → global optimized → base."""
    opt_dir = STRATEGY_DIR / "optimized"
    if ticker:
        leap_opt = opt_dir / f"{path.stem}_{ticker}_leaps_{option_type}_optimized.yaml"
        if leap_opt.exists():
            return leap_opt
        ticker_opt = opt_dir / f"{path.stem}_{ticker}_optimized.yaml"
        if ticker_opt.exists():
            return ticker_opt
    global_leap = opt_dir / f"{path.stem}_leaps_{option_type}_optimized.yaml"
    if global_leap.exists():
        return global_leap
    global_opt = opt_dir / f"{path.stem}_optimized.yaml"
    if global_opt.exists():
        return global_opt
    return path


def _print_results(all_results):
    rows = []
    for r in all_results:
        if r:
            rows.append(r)

    if not rows:
        print("  No results.")
        return

    rows.sort(key=lambda x: x["net_pnl"], reverse=True)

    width = 80
    print(f"\n{'='*width}")
    print(f"{'LEAP BACKTEST RESULTS':^{width}}")
    print(f"{'='*width}")
    print(f"  {'Rank':<5} {'Ticker':<8} {'Strategy':<26} {'Type':<5} "
          f"{'P&L':>10} {'Win%':>7} {'Avg%':>8} {'Trades':>7}")
    print(f"  {'-'*75}")

    for rank, r in enumerate(rows, 1):
        marker = "  ◀ BEST" if rank == 1 else ""
        print(f"  {rank:<5} {r['ticker']:<8} {r['strategy']:<26} {r['option_type'].upper():<5} "
              f"${r['net_pnl']:>9.2f} {r['win_rate']:>6.1%} {r['avg_pnl_pct']:>7.1f}% "
              f"{r['trades']:>7}{marker}")

    print(f"\n  Pricing: Black-Scholes with 30-bar realized vol (approximate)")
    print(f"{'='*width}\n")


@click.command("leaps-backtest")
@click.argument("target", required=False, default=None, metavar="[TICKER|CATEGORY|all]")
@click.option("--strategy", default=None,
              help="Strategy YAML (e.g. rsi.yaml). Omit for --all-strategies.")
@click.option("--all-strategies", "all_strategies", is_flag=True,
              help="Run the curated active strategy set (config.yaml: active_strategies)")
@click.option("--every-strategy", "every_strategy", is_flag=True,
              help="Run EVERY strategy YAML (full sweep; implies --all-strategies)")
@click.option("--option-type", "option_type",
              type=click.Choice(["call", "put", "auto"]), default="auto", show_default=True,
              help="'call'=bullish signals only, 'put'=bearish only, 'auto'=both")
@click.option("--interval", type=click.Choice(["1d", "1wk"]), default="1wk", show_default=True)
@click.option("--leap-days", "leap_days", default=365, show_default=True,
              help="Option duration in days at entry")
@click.option("--strike-moneyness", "strike_moneyness", default=1.0, show_default=True,
              help="Strike as fraction of spot (1.0=ATM, 0.95=slightly ITM call)")
@click.option("--stop-loss", "stop_loss_pct", default=0.50, show_default=True,
              help="Close if option loses this fraction of entry premium")
def leaps_backtest(target, strategy, all_strategies, every_strategy, option_type, interval,
                   leap_days, strike_moneyness, stop_loss_pct):
    """Backtest LEAP call/put options using Black-Scholes pricing on historical data.

    Premiums are approximated via Black-Scholes with 30-bar realized volatility
    since yfinance doesn't provide historical options prices. Results are
    directionally useful but not exact.

    Examples:\n
      stonks leaps-backtest AAPL --strategy rsi.yaml\n
      stonks leaps-backtest stocks --all-strategies --option-type put\n
      stonks leaps-backtest NVDA --all-strategies --interval 1wk\n
      stonks leaps-backtest etfs --all-strategies --option-type auto
    """
    from stonkslib.backtest.leaps import run_leaps_backtest

    if not target:
        print("[!] Provide a ticker, category, or 'all'")
        return
    if not strategy and not all_strategies and not every_strategy:
        print("[!] Provide --strategy <file>, --all-strategies, or --every-strategy")
        return

    tickers = _resolve_tickers(target)
    strategy_paths = (resolve_strategy_set(every=every_strategy)
                      if (all_strategies or every_strategy) else [STRATEGY_DIR / strategy])

    missing = [p for p in strategy_paths if not p.exists()]
    if missing:
        for p in missing:
            print(f"[!] Strategy not found: {p}")
        return

    print(f"\nBacktesting {len(tickers)} ticker(s) × {len(strategy_paths)} strategy(s) "
          f"[{option_type} | {interval} | {leap_days}d LEAP]...\n")

    all_results = []
    for path in strategy_paths:
        for ticker in tickers:
            resolved = _resolve_strategy_path(path, ticker, option_type)
            with open(resolved) as f:
                strat = yaml.safe_load(f)

            result = run_leaps_backtest(
                ticker=ticker,
                interval=interval,
                strategy=strat,
                option_type=option_type,
                leap_days=leap_days,
                strike_moneyness=strike_moneyness,
                stop_loss_pct=stop_loss_pct,
            )
            if result:
                all_results.append(result)

    _print_results(all_results)
