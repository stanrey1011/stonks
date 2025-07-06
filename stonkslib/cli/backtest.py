import click
from stonkslib.utils.load_strategy import load_strategy_config

from stonkslib.backtest.indicators import run_all_backtests as backtest_indicators
try:
    from stonkslib.backtest.doubles import run_all_backtests as backtest_doubles
except ImportError:
    backtest_doubles = None
try:
    from stonkslib.backtest.triangles import run_all_backtests as backtest_triangles
except ImportError:
    backtest_triangles = None
try:
    from stonkslib.backtest.head_shoulders import run_all_backtests as backtest_head_shoulders
except ImportError:
    backtest_head_shoulders = None
try:
    from stonkslib.backtest.wedges import run_all_backtests as backtest_wedges
except ImportError:
    backtest_wedges = None

@click.command()
@click.option(
    "--target",
    type=click.Choice(["all", "indicators", "doubles", "triangles", "head_shoulders", "wedges"]),
    default="all",
    help="Which backtests to run: indicators, doubles, triangles, head_shoulders, wedges, or all",
)
@click.option(
    "--config",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to strategy YAML config file (default: None for hardcoded backtest logic)",
)
def backtest(target, config):
    """Run backtests on merged data, using a strategy config if provided."""
    strategy = None
    if config:
        print(f"[*] Loading strategy config: {config}")
        strategy = load_strategy_config(config)
    ran = False
    if target in ("all", "indicators"):
        print("[*] Running indicator backtest...")
        backtest_indicators(strategy)
        ran = True
    if target in ("all", "doubles") and backtest_doubles:
        print("[*] Running doubles pattern backtest...")
        backtest_doubles(strategy)
        ran = True
    if target in ("all", "triangles") and backtest_triangles:
        print("[*] Running triangles pattern backtest...")
        backtest_triangles(strategy)
        ran = True
    if target in ("all", "head_shoulders") and backtest_head_shoulders:
        print("[*] Running head-shoulders pattern backtest...")
        backtest_head_shoulders(strategy)
        ran = True
    if target in ("all", "wedges") and backtest_wedges:
        print("[*] Running wedges pattern backtest...")
        backtest_wedges(strategy)
        ran = True
    if not ran:
        print("[!] No backtest ran (perhaps module missing or typo in --target)")
