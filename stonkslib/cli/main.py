# stonkslib/cli/main.py
import click
from stonkslib.cli.fetch import fetch  # Correct path
from stonkslib.cli.clean import clean
from stonkslib.cli.analyze import analyze
from stonkslib.cli.merge import merge
from stonkslib.cli.backtest import backtest

@click.group()
def cli():
    """Stonks CLI"""

cli.add_command(fetch)
cli.add_command(clean)
cli.add_command(analyze)
cli.add_command(merge)
cli.add_command(backtest)

if __name__ == "__main__":
    cli(auto_envvar_prefix="STONKS", standalone_mode=True)