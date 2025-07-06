import click
from .fetch import fetch
from .clean import clean
from .analyze import analyze
from .merge import merge
from .backtest import backtest

@click.group()
def cli():
    """Stonks CLI"""

cli.add_command(fetch)
cli.add_command(clean)
cli.add_command(analyze)
cli.add_command(merge)
cli.add_command(backtest)

if __name__ == "__main__":
    # Enable Click shell completion support
    cli(auto_envvar_prefix="STONKS", standalone_mode=True)
