import click
import yaml
from pathlib import Path
from stonkslib.utils.logging import setup_logging

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = PROJECT_ROOT / "stonkslib" / "strategies"
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
logger = setup_logging(PROJECT_ROOT / "log", "optimize.log")


def _load_all_tickers():
    with open(TICKER_YAML) as f:
        data = yaml.safe_load(f)
    return [t for category in data.values() for t in category]


def _load_all_strategies():
    return [p for p in STRATEGY_DIR.glob("*.yaml")]


def _print_summary(results):
    rows = []
    for strategy_name, result in results.items():
        if not result or not result.get("best_metrics"):
            continue
        metrics_list = result["best_metrics"]
        avg_pnl = sum(m["net_pnl"] for m in metrics_list) / len(metrics_list)
        avg_win = sum(m["win_rate"] for m in metrics_list) / len(metrics_list)
        total_trades = sum(m["trades"] for m in metrics_list)
        rows.append((strategy_name, avg_pnl, avg_win, total_trades, result.get("out_path", "")))

    rows.sort(key=lambda r: r[1], reverse=True)

    print(f"\n{'='*65}")
    print(f"{'STRATEGY OPTIMIZATION RESULTS':^65}")
    print(f"{'='*65}")
    print(f"{'Rank':<5} {'Strategy':<28} {'Avg P&L':>10} {'Win Rate':>10} {'Trades':>8}")
    print(f"{'-'*65}")
    for rank, (name, pnl, win, trades, path) in enumerate(rows, 1):
        marker = " ◀ BEST" if rank == 1 else ""
        print(f"{rank:<5} {name:<28} ${pnl:>9.2f} {win:>9.1%} {trades:>8}{marker}")
    print(f"{'='*65}")
    if rows:
        print(f"\nBest strategy: {rows[0][0]}")
        print(f"Optimized YAML: {rows[0][4]}")


@click.command()
@click.option("--strategy", default=None,
              help="Strategy YAML filename (e.g. rsi_macd.yaml). Omit for --all-strategies.")
@click.option("--all-strategies", "all_strategies", is_flag=True,
              help="Run optimization on all strategy YAMLs in stonkslib/strategies/")
@click.option("--ticker", default=None,
              help="Single ticker to optimize against (e.g. AAPL).")
@click.option("--all-tickers", "all_tickers", is_flag=True,
              help="Optimize across all tickers in tickers.yaml")
@click.option("--per-ticker", "per_ticker", is_flag=True,
              help="Save a separate optimized YAML per ticker (e.g. rsi_AAPL_optimized.yaml). "
                   "Without this flag, all tickers are averaged into one global file.")
@click.option("--interval",
              type=click.Choice(["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]),
              default="1d", show_default=True)
@click.option("--iterations", default=5, show_default=True,
              help="Number of LLM optimization iterations per strategy")
@click.option("--model", default="qwen2.5:7b", show_default=True,
              help="Ollama model to use")
@click.option("--leaps", "use_leaps", is_flag=True,
              help="Score against the LEAP backtest (Black-Scholes pricing) instead of equity. "
                   "Saves separate _leaps_{type}_optimized.yaml files.")
@click.option("--option-type", "option_type",
              type=click.Choice(["call", "put", "auto"]), default="auto", show_default=True,
              help="Option direction for LEAP optimization (only used with --leaps)")
def optimize(strategy, all_strategies, ticker, all_tickers, per_ticker, interval, iterations, model, use_leaps, option_type):
    """LLM-driven parameter optimization across strategies and tickers.

    Use --per-ticker to save a separate optimized YAML per ticker.
    Use --leaps to optimize signal params for LEAP options instead of equity —
    the LLM scores on avg trade return % and biases toward fewer, stronger signals.

    Examples:\n
      stonks optimize --strategy rsi.yaml --ticker AAPL --per-ticker\n
      stonks optimize --strategy rsi.yaml --ticker NVDA --leaps --option-type call\n
      stonks optimize --all-strategies --all-tickers --per-ticker --leaps --option-type put\n
      stonks optimize --all-strategies --all-tickers --iterations 3
    """
    from stonkslib.llm.optimizer import optimize as run_optimize
    from stonkslib.backtest.strategy import load_strategy

    if not strategy and not all_strategies:
        print("[!] Provide --strategy <file> or --all-strategies")
        return
    if not ticker and not all_tickers:
        print("[!] Provide --ticker <TICKER> or --all-tickers")
        return

    tickers = _load_all_tickers() if all_tickers else [ticker]
    strategy_paths = _load_all_strategies() if all_strategies else [STRATEGY_DIR / strategy]

    missing = [p for p in strategy_paths if not p.exists()]
    if missing:
        for p in missing:
            logger.error(f"[!] Strategy file not found: {p}")
        return

    results = {}

    for path in strategy_paths:
        name = load_strategy(path).get("name", path.stem)

        mode_label = f"LEAP {option_type}" if use_leaps else "equity"

        if per_ticker:
            for t in tickers:
                print(f"\n{'─'*50}")
                print(f"Strategy: {name}  |  Ticker: {t}  |  {mode_label}  |  Iterations: {iterations}")
                print(f"{'─'*50}")
                result = run_optimize(
                    strategy_path=path,
                    tickers=[t],
                    interval=interval,
                    iterations=iterations,
                    model=model,
                    output_ticker=t,
                    use_leaps=use_leaps,
                    option_type=option_type,
                )
                results[f"{name} / {t}"] = result or {}
        else:
            print(f"\n{'─'*50}")
            print(f"Strategy: {name}  |  Tickers: {tickers}  |  {mode_label}  |  Iterations: {iterations}")
            print(f"{'─'*50}")
            result = run_optimize(
                strategy_path=path,
                tickers=tickers,
                interval=interval,
                iterations=iterations,
                model=model,
                use_leaps=use_leaps,
                option_type=option_type,
            )
            results[name] = result or {}

    _print_summary(results)
