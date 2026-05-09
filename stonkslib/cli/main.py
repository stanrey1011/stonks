# stonkslib/cli/main.py
import click
from stonkslib.cli.fetch import fetch
from stonkslib.cli.clean import clean
from stonkslib.cli.analyze import analyze
from stonkslib.cli.merge import merge
from stonkslib.cli.backtest import backtest
from stonkslib.cli.export import export
from stonkslib.cli.optimize import optimize
from stonkslib.cli.alert import alert
from stonkslib.cli.tickers import tickers
from stonkslib.cli.bot import bot


@click.group()
def cli():
    """Stonks CLI"""

cli.add_command(fetch)
cli.add_command(clean)
cli.add_command(analyze)
cli.add_command(merge)
cli.add_command(backtest)
cli.add_command(export)
cli.add_command(optimize)
cli.add_command(alert)
cli.add_command(tickers)
cli.add_command(bot)

if __name__ == "__main__":
    cli(auto_envvar_prefix="STONKS", standalone_mode=True)