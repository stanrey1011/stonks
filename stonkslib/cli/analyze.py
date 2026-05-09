import click
import yaml
from pathlib import Path
from stonkslib.utils.logging import setup_logging
from stonkslib.analysis.signals import aggregate_and_save
from stonkslib.merge.by_indicators import merge_signals_for_ticker_interval
from stonkslib.merge.by_patterns import merge_patterns_for_ticker_interval

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
logger = setup_logging(PROJECT_ROOT / "log", "analyze.log")

INTERVALS = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]


def _resolve_tickers(target):
    with open(TICKER_YAML) as f:
        data = yaml.safe_load(f) or {}
    if not target or target.lower() == "all":
        return [t for items in data.values() for t in (items or [])]
    for cat, tickers in data.items():
        if cat.lower() == target.lower():
            return tickers or []
    return [target.upper()]


@click.command()
@click.argument("target", required=False, default=None,
                metavar="[TICKER|CATEGORY|all]")
@click.option("--interval", type=click.Choice(INTERVALS), default="1d", show_default=True)
def analyze(target, interval):
    """Run indicators, detect patterns, and merge signals.

    TARGET can be a ticker (AAPL), a category (stocks/etfs/crypto), or 'all'.\n

    Examples:\n
      stonks analyze AAPL --interval 1d\n
      stonks analyze crypto --interval 1wk\n
      stonks analyze all
    """
    if not target:
        target = "all"

    tickers = _resolve_tickers(target)

    for t in tickers:
        try:
            aggregate_and_save(t, interval)
            logger.info(f"[✓] Analyzed {t} ({interval})")
        except Exception as e:
            logger.error(f"[!] Analyze {t} ({interval}): {e}")
        try:
            merge_signals_for_ticker_interval(t, interval)
            merge_patterns_for_ticker_interval(t, interval)
            logger.info(f"[✓] Merged {t} ({interval})")
        except Exception as e:
            logger.error(f"[!] Merge {t} ({interval}): {e}")

    print(f"[✓] Done — {len(tickers)} ticker(s) analyzed and merged ({interval})")
