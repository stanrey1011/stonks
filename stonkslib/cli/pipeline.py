import click
import yaml
from pathlib import Path
from stonkslib.utils.logging import setup_logging

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
logger = setup_logging(PROJECT_ROOT / "log", "pipeline.log")

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


def run_pipeline(ticker, interval, force=False):
    """Run fetch → clean → analyze for a single ticker/interval."""
    import yaml as _yaml
    import os
    from pathlib import Path as _Path

    _root = _Path(__file__).resolve().parents[2]
    with open(_root / "config.yaml") as f:
        cfg = _yaml.safe_load(f)

    from stonkslib.fetch.td import fetch_all
    from stonkslib.clean.td import clean_td
    from stonkslib.analysis.signals import aggregate_and_save
    from stonkslib.merge.by_indicators import merge_signals_for_ticker_interval
    from stonkslib.merge.by_patterns import merge_patterns_for_ticker_interval

    ticker_yaml = _root / cfg["project"]["ticker_yaml"]
    data_dir = _root / cfg["project"]["ticker_data_dir"]

    try:
        fetch_all(yaml_file=ticker_yaml, data_dir=data_dir, force=force, tickers=[ticker])
        logger.info(f"[✓] Fetched {ticker}")
    except Exception as e:
        logger.error(f"[!] Fetch {ticker}: {e}")
        return False

    try:
        clean_td(ticker, interval, force=force)
        logger.info(f"[✓] Cleaned {ticker} ({interval})")
    except Exception as e:
        logger.error(f"[!] Clean {ticker} ({interval}): {e}")

    try:
        aggregate_and_save(ticker, interval)
        merge_signals_for_ticker_interval(ticker, interval)
        merge_patterns_for_ticker_interval(ticker, interval)
        logger.info(f"[✓] Analyzed {ticker} ({interval})")
    except Exception as e:
        logger.error(f"[!] Analyze {ticker} ({interval}): {e}")

    # Earnings data — skip crypto, fetch once per ticker (not per interval)
    if interval == "1d":
        try:
            from stonkslib.utils.earnings import fetch_and_save
            fetch_and_save(ticker)
            logger.info(f"[✓] Earnings saved {ticker}")
        except Exception as e:
            logger.warning(f"[!] Earnings {ticker}: {e}")

    return True


@click.command()
@click.argument("target", required=False, default=None,
                metavar="[TICKER|CATEGORY|all]")
@click.option("--interval", type=click.Choice(INTERVALS), default="1d", show_default=True)
@click.option("--force", is_flag=True, help="Force re-fetch even if data is fresh")
def pipeline(target, interval, force):
    """Run the full pipeline: fetch → clean → analyze.

    TARGET can be a ticker (AAPL), a category (stocks/etfs/crypto), or 'all'.\n

    Examples:\n
      stonks pipeline AAPL\n
      stonks pipeline crypto --interval 1wk\n
      stonks pipeline all --interval 1d --force
    """
    if not target:
        target = "all"

    tickers = _resolve_tickers(target)
    if not tickers:
        print(f"[!] No tickers found for: {target}")
        return

    print(f"[→] Pipeline: {len(tickers)} ticker(s), interval={interval}")
    ok = 0
    for t in tickers:
        if run_pipeline(t, interval, force=force):
            ok += 1

    print(f"[✓] Done — {ok}/{len(tickers)} ticker(s) completed ({interval})")
