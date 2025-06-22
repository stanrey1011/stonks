import os
import click
from stonkslib.utils.fetch_ranges import fetch_all
from stonkslib.patterns.historical_pattern_analysis import main as anal_main
from stonkslib.check_data_span import main as check_span

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@click.group()
def cli():
    """Stonks CLI tool"""
    pass

@cli.command(name="fetch")
def fetch_cmd():
    """Fetch all tickers from tickers.yaml (default range: 1y)"""
    fetch_all()

@cli.command(name="anal")
def analyze():
    """Run historical pattern analysis"""
    anal_main()

@cli.command(name="span")
def span():
    """Check available data span for each ticker"""
    check_span()

@cli.command(name="wipe-imports")
def wipe_imports():
    """Delete all fetched CSVs (except historical analysis output)"""
    data_dir = os.path.join(BASE_DIR, "..", "data")
    for root, _, files in os.walk(data_dir):
        for file in files:
            if file.endswith(".csv") and file != "historical_pattern_analysis.csv":
                os.remove(os.path.join(root, file))
    click.echo("🧹 Wiped imported CSVs.")

@cli.command(name="wipe-anal")
def wipe_analysis():
    """Delete the historical analysis CSV file"""
    analysis_path = os.path.join(BASE_DIR, "..", "data", "ticker_data", "historical_pattern_analysis.csv")
    if os.path.exists(analysis_path):
        os.remove(analysis_path)
        click.echo("🧽 Wiped analysis file.")
    else:
        click.echo("⚠ No analysis file found.")

if __name__ == "__main__":
    cli()
