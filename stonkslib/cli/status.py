import click
import yaml
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
STRATEGY_DIR = PROJECT_ROOT / "stonkslib" / "strategies"
CLEAN_DIR = PROJECT_ROOT / "data" / "ticker_data" / "clean"

INTERVALS = ["1d", "1wk", "1h", "30m", "15m", "5m", "1m"]


def _age(path):
    """Return human-readable age of a file."""
    mtime = path.stat().st_mtime
    delta = datetime.now().timestamp() - mtime
    if delta < 3600:
        return f"{int(delta/60)}m"
    if delta < 86400:
        return f"{int(delta/3600)}h"
    return f"{int(delta/86400)}d"


@click.command()
def status():
    """Show data freshness and which strategies are optimized.

    Example:\n
      stonks status
    """
    with open(TICKER_YAML) as f:
        data = yaml.safe_load(f) or {}

    all_tickers = [(t, cat) for cat, items in data.items() for t in (items or [])]
    total = len(all_tickers)

    print(f"\n{'='*65}")
    print(f"  Stonks Status")
    print(f"{'='*65}")

    # --- Watchlist ---
    print(f"\n  Watchlist: {total} tickers")
    for cat, items in data.items():
        tlist = ", ".join(items or [])
        print(f"    {cat:<8}  {tlist}")

    # --- Data freshness ---
    print(f"\n  Data Freshness (clean parquet):")
    print(f"    {'Ticker':<10}", end="")
    for iv in INTERVALS:
        print(f"  {iv:>4}", end="")
    print()
    print(f"    {'-'*55}")

    for ticker, _ in all_tickers:
        ticker_dir = CLEAN_DIR / ticker
        print(f"    {ticker:<10}", end="")
        for iv in INTERVALS:
            p = ticker_dir / f"{iv}.parquet"
            if p.exists():
                print(f"  {_age(p):>4}", end="")
            else:
                print(f"  {'—':>4}", end="")
        print()

    # --- Optimized strategies ---
    from stonkslib.utils.active_strategies import active_strategy_names
    all_strategies = list(STRATEGY_DIR.glob("*.yaml"))
    optimized_dir = STRATEGY_DIR / "optimized"
    optimized = {p.stem.replace("_optimized", "") for p in optimized_dir.glob("*_optimized.yaml")} \
        if optimized_dir.exists() else set()
    active = set(active_strategy_names())

    print(f"\n  Strategies ({len(all_strategies)} total, {len(active)} active, {len(optimized)} optimized):")
    for path in sorted(all_strategies):
        stem = path.stem
        has_opt = stem in optimized
        opt_marker = "✓ opt" if has_opt else "     "
        active_marker = "★" if stem in active else " "
        with open(path) as f:
            strat = yaml.safe_load(f) or {}
        name = strat.get("name", stem)
        print(f"    {active_marker} [{opt_marker}] {name}")
    print("    (★ = in active set used by default fan-outs)")

    print(f"\n{'='*65}\n")
