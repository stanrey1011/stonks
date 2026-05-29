import click
import yaml
from pathlib import Path
from stonkslib.utils.logging import setup_logging

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = PROJECT_ROOT / "stonkslib" / "strategies"
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
logger = setup_logging(PROJECT_ROOT / "log", "alert.log")


def _resolve_tickers(target):
    with open(TICKER_YAML) as f:
        data = yaml.safe_load(f) or {}
    if not target or target.lower() == "all":
        return [t for items in data.values() for t in (items or [])]
    for cat, tickers in data.items():
        if cat.lower() == target.lower():
            return tickers or []
    return [target.upper()]


def _load_all_strategies():
    return list(STRATEGY_DIR.glob("*.yaml"))


def _resolve_strategy_path(path, ticker=None):
    """Return optimized strategy, preferring ticker-specific over global over base."""
    opt_dir = STRATEGY_DIR / "optimized"
    if ticker:
        ticker_opt = opt_dir / f"{path.stem}_{ticker}_optimized.yaml"
        if ticker_opt.exists():
            return ticker_opt
    global_opt = opt_dir / f"{path.stem}_optimized.yaml"
    if global_opt.exists():
        return global_opt
    return path


def _print_signals(all_signals):
    buys = [s for s in all_signals if s["type"] == "BUY"]
    sells = [s for s in all_signals if s["type"] == "SELL"]

    print(f"\n{'='*65}")
    print(f"{'ALERT SCAN RESULTS':^65}")
    print(f"{'='*65}")

    if not all_signals:
        print("  No signals fired on the latest bar.")
    else:
        if buys:
            print(f"\n  BUY signals ({len(buys)}):")
            for s in buys:
                print(f"    {s['ticker']:<8} [{s['interval']}]  ${s['close']:.2f}  {s['date']}")
                print(f"             Reason: {s['reason']}")
                if s.get("llm_conviction"):
                    print(f"             LLM: [{s['llm_conviction'].upper()}] {s['llm_reasoning']}")
        if sells:
            print(f"\n  SELL signals ({len(sells)}):")
            for s in sells:
                print(f"    {s['ticker']:<8} [{s['interval']}]  ${s['close']:.2f}  {s['date']}")
                print(f"             Reason: {s['reason']}")
                if s.get("llm_conviction"):
                    print(f"             LLM: [{s['llm_conviction'].upper()}] {s['llm_reasoning']}")

    print(f"\n{'='*65}\n")


@click.command()
@click.argument("target", required=False, default=None,
                metavar="[TICKER|CATEGORY|all]")
@click.option("--strategy", default=None,
              help="Strategy YAML filename (e.g. rsi.yaml). Omit for --all-strategies.")
@click.option("--all-strategies", "all_strategies", is_flag=True,
              help="Scan using all strategy YAMLs")
@click.option("--interval",
              type=click.Choice(["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]),
              default="1d", show_default=True)
@click.option("--min-signals", "min_signals", default=1, show_default=True,
              help="Minimum indicators that must agree (BUY or SELL) before alerting")
@click.option("--confirm-weekly", "confirm_weekly", is_flag=True,
              help="For 1d alerts: require the weekly 20/50 EMA trend to align with signal direction")
@click.option("--llm-interpret", "llm_interpret", is_flag=True,
              help="Use LLM to assess conviction and add plain-English reasoning to each signal")
@click.option("--llm-model", "llm_model", default="qwen2.5:7b", show_default=True,
              help="Ollama model for signal interpretation")
def alert(target, strategy, all_strategies, interval, min_signals, confirm_weekly,
          llm_interpret, llm_model):
    """Scan latest bar for entry/exit signals. Auto-uses optimized strategies when available.

    TARGET can be a ticker (AAPL), a category (stocks/etfs/crypto), or 'all'.\n

    Examples:\n
      stonks alert AAPL --strategy rsi.yaml\n
      stonks alert all --all-strategies --interval 1d\n
      stonks alert crypto --all-strategies --interval 1wk
    """
    from stonkslib.alerts.signals import check_signals

    if not target:
        print("[!] Provide a ticker (AAPL), category (stocks/etfs/crypto), or 'all'")
        return
    if not strategy and not all_strategies:
        print("[!] Provide --strategy <file> or --all-strategies")
        return

    tickers = _resolve_tickers(target)

    if all_strategies:
        strategy_paths = _load_all_strategies()
    else:
        strategy_paths = [STRATEGY_DIR / strategy]

    missing = [p for p in strategy_paths if not p.exists()]
    if missing:
        for p in missing:
            print(f"[!] Strategy file not found: {p}")
        return

    all_signals = []

    for path in strategy_paths:
        strat_name = yaml.safe_load(open(path)).get("name", path.stem)
        print(f"\nStrategy: {strat_name}")

        for t in tickers:
            resolved = _resolve_strategy_path(path, ticker=t)
            if resolved != path:
                logger.info(f"[opt] {t}: using {resolved.name}")

            with open(resolved) as f:
                strat = yaml.safe_load(f)

            signals = check_signals(t, interval, strat,
                                   min_signals=min_signals,
                                   confirm_weekly=confirm_weekly,
                                   llm_interpret=llm_interpret,
                                   llm_model=llm_model)
            if signals is None:
                logger.warning(f"[!] Skipped {t} — no data")
                continue
            if signals:
                for s in signals:
                    s["strategy"] = strat_name
                all_signals.extend(signals)
                for s in signals:
                    logger.info(f"[{s['type']}] {t} ({interval}) — {s['reason']} @ ${s['close']}")

    _print_signals(all_signals)
