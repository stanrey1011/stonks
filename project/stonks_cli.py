import click
from project.fetch_data import main as fetch_main
from project.patterns.historical_pattern_analysis import main as anal_main
from project.check_data_span import main as check_span
import os
import shutil

@click.group()
def cli():
    """Stonks CLI tool"""
    pass

@cli.command()
def fetch():
    """Fetch latest ticker data"""
    fetch_main()

@cli.command(name="anal")
def analyze():
    """Run pattern analysis on tickers"""
    anal_main()

@cli.command()
def span():
    """Show data span"""
    check_span()

@cli.command(name="wipe-imports")
def wipe_imports():
    """Wipe imported CSVs (fetched ticker data)"""
    data_dir = "data/ticker_data"
    for file in os.listdir(data_dir):
        if file.endswith(".csv") and file != "historical_pattern_analysis.csv":
            os.remove(os.path.join(data_dir, file))
    click.echo("🧹 Wiped imported data.")

@cli.command(name="wipe-anal")
def wipe_analysis():
    """Wipe historical analysis file"""
    path = "data/ticker_data/historical_pattern_analysis.csv"
    if os.path.exists(path):
        os.remove(path)
        click.echo("🧽 Wiped analysis file.")
    else:
        click.echo("No analysis file found.")

if __name__ == "__main__":
    cli()
