import click
import yaml
import os
from pathlib import Path
from stonkslib.fetch.td import fetch_all
from stonkslib.fetch.od import fetch_all_options, load_tickers as load_od_tickers
from stonkslib.utils.logging import setup_logging

PROJECT_ROOT = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
with open(PROJECT_ROOT / "config.yaml") as f:
    config = yaml.safe_load(f)

TICKER_YAML = PROJECT_ROOT / config["project"]["ticker_yaml"]
DATA_DIR = PROJECT_ROOT / config["project"]["ticker_data_dir"]
logger = setup_logging(PROJECT_ROOT / "log", "fetch.log")

VALID_CATEGORIES = ["stocks", "etfs", "crypto"]


def _resolve_tickers(target):
    with open(TICKER_YAML) as f:
        data = yaml.safe_load(f) or {}
    if not target or target.lower() == "all":
        return [t for items in data.values() for t in (items or [])], None
    for cat, tickers in data.items():
        if cat.lower() == target.lower():
            return tickers or [], cat
    return [target.upper()], None


class DefaultToData(click.Group):
    """Routes to the 'data' subcommand when no recognized subcommand is given."""
    def resolve_command(self, ctx, args):
        if not args or args[0] not in self.commands:
            args.insert(0, "data")
        return super().resolve_command(ctx, args)


@click.group(cls=DefaultToData)
def fetch():
    """Fetch raw OHLCV or options data.

    With no subcommand, fetches OHLCV data (shortcut for 'fetch data').\n

    Examples:\n
      stonks fetch               (all tickers)\n
      stonks fetch AAPL\n
      stonks fetch crypto\n
      stonks fetch --force
    """


@fetch.command()
@click.argument("target", required=False, default=None,
                metavar="[TICKER|CATEGORY|all]")
@click.option("--force", is_flag=True, help="Force re-download even if data is fresh")
def data(target, force):
    """Fetch OHLCV data. Target defaults to all tickers."""
    if not target:
        target = "all"

    tickers, category = _resolve_tickers(target)
    if not tickers:
        print(f"[!] No tickers found for: {target}")
        return

    if category:
        fetch_all(yaml_file=TICKER_YAML, data_dir=DATA_DIR, force=force, category=category)
    elif target.lower() == "all":
        for cat in VALID_CATEGORIES:
            fetch_all(yaml_file=TICKER_YAML, data_dir=DATA_DIR, force=force, category=cat)
    else:
        fetch_all(yaml_file=TICKER_YAML, data_dir=DATA_DIR, force=force, tickers=tickers)


@fetch.group()
def options():
    """Fetch option chains."""


@options.group()
def buy():
    """Buy side options."""


@options.group()
def sell():
    """Sell side options."""


def _run_options_fetch(side, option_type, term, ticker, strategy=None):
    strategy_name = strategy or term
    strat_config = config["strategies"].get(strategy_name, {
        "min_dte": 21, "max_dte": 45,
        "option_type": option_type, "side": side,
        "output_dir": f"{option_type}/{side}/{strategy_name}"
    })
    output_dir = PROJECT_ROOT / config["project"]["options_data_dir"] / strat_config["output_dir"]
    fetch_all_options(
        output_dir=output_dir,
        min_days_out=strat_config["min_dte"],
        max_days_out=strat_config["max_dte"],
        option_type=strat_config["option_type"],
        symbols=[ticker] if ticker else load_od_tickers()
    )
    print(f"[✓] Options saved to {output_dir}")


for _side, _grp in [("buy", buy), ("sell", sell)]:
    for _term in ["leaps", "weekly", "monthly", "custom"]:
        def _make_cmd(side=_side, term=_term):
            @click.option("--option_type", type=click.Choice(["calls", "puts"]), default="calls")
            @click.option("--ticker", default=None)
            def _cmd(option_type, ticker, side=side, term=term):
                _run_options_fetch(side, option_type, term, ticker)
            _cmd.__name__ = term
            return click.command(term)(_cmd)
        _grp.add_command(_make_cmd())


@sell.command("covered_calls")
@click.option("--ticker", default=None)
@click.option("--term", type=click.Choice(["weekly", "monthly", "leaps", "custom"]), default="monthly")
def covered_calls(term, ticker):
    """Fetch covered call chains."""
    _run_options_fetch("sell", "calls", term, ticker, strategy="covered_calls")


@sell.command("secured_puts")
@click.option("--ticker", default=None)
@click.option("--term", type=click.Choice(["weekly", "monthly", "leaps", "custom"]), default="monthly")
def secured_puts(term, ticker):
    """Fetch secured put chains."""
    _run_options_fetch("sell", "puts", term, ticker, strategy="secured_puts")
