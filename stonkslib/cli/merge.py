import click

from stonkslib.merge.by_indicators import run_merge_indicators, merge_signals_for_ticker_interval
from stonkslib.merge.by_patterns import run_merge_patterns, merge_patterns_for_ticker_interval

@click.command()
@click.option(
    "--target",
    type=click.Choice(["indicators", "patterns", "all"]),
    default="all",
    help="Which data to merge: indicators, patterns, or all",
)
@click.option(
    "--ticker",
    type=str,
    default=None,
    help="Limit merging to a specific ticker",
)
@click.option(
    "--interval",
    type=str,
    default=None,
    help="Limit merging to a specific interval",
)
def merge(target, ticker, interval):
    """Merge signals into combined time series format."""
    if target in ("indicators", "all"):
        if ticker and interval:
            merge_signals_for_ticker_interval(ticker, interval)
        else:
            run_merge_indicators()

    if target in ("patterns", "all"):
        if ticker and interval:
            merge_patterns_for_ticker_interval(ticker, interval)
        else:
            run_merge_patterns()
