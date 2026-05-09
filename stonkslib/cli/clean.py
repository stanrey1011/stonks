import click
import yaml
from pathlib import Path
from stonkslib.utils.logging import setup_logging
from stonkslib.clean.td import clean_td

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
logger = setup_logging(PROJECT_ROOT / "log", "clean.log")

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


class DefaultToData(click.Group):
    """Routes to the 'data' subcommand when no recognized subcommand is given."""
    def resolve_command(self, ctx, args):
        if not args or args[0] not in self.commands:
            args.insert(0, "data")
        return super().resolve_command(ctx, args)


@click.group(cls=DefaultToData)
def clean():
    """Clean raw OHLCV or options data.

    With no subcommand, cleans OHLCV data (shortcut for 'clean data').\n

    Examples:\n
      stonks clean               (all tickers, all intervals)\n
      stonks clean AAPL\n
      stonks clean crypto --interval 1d\n
      stonks clean options AAPL
    """


@clean.command()
@click.argument("target", required=False, default=None,
                metavar="[TICKER|CATEGORY|all]")
@click.option("--interval", type=click.Choice(INTERVALS), default=None,
              help="Specific interval (default: all)")
@click.option("--force", is_flag=True, help="Overwrite existing clean files")
def data(target, interval, force):
    """Clean OHLCV data. Target defaults to all tickers."""
    if not target:
        target = "all"

    tickers = _resolve_tickers(target)
    intervals = [interval] if interval else INTERVALS

    for t in tickers:
        for i in intervals:
            try:
                df = clean_td(t, i, force=force)
                if df is not None:
                    logger.info(f"[✓] Cleaned {t} ({i}) — {len(df)} rows")
            except Exception as e:
                logger.error(f"[!] {t} ({i}): {e}")


@clean.command()
@click.argument("ticker", required=False, default=None)
@click.option("--strategy", default=None, help="Options strategy name")
@click.option("--force", is_flag=True)
def options(ticker, strategy, force):
    """Clean options data."""
    from stonkslib.clean.od import clean_options_data
    try:
        with open(PROJECT_ROOT / "config.yaml") as f:
            config = yaml.safe_load(f)
    except Exception:
        config = {"strategies": {}}

    with open(TICKER_YAML) as f:
        raw = yaml.safe_load(f) or {}
    all_tickers = [t for items in raw.values() for t in (items or [])]
    tickers = [ticker.upper()] if ticker else all_tickers
    strategies = [strategy] if strategy else list(config.get("strategies", {}).keys())

    for t in tickers:
        for s in strategies:
            sc = config.get("strategies", {}).get(s, {})
            try:
                df = clean_options_data(t, s, side=sc.get("side", "buy"),
                                        option_type=sc.get("type", "calls"), force=force)
                if df is not None:
                    logger.info(f"[✓] Cleaned options {t} ({s})")
            except Exception as e:
                logger.error(f"[!] {t} ({s}): {e}")
