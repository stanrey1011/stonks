import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

import click
import os
import shutil
from fetch_data import main as fetch_main
from stonkslib.patterns.historical_pattern_analysis import main as analyze_main, scan_ticker

@click.group()
def cli():
    """Stonks CLI – analyze, fetch, or wipe pattern data"""
    pass

@cli.command()
def fetch():
    """Fetch ticker data"""
    fetch_main()

@cli.command(name="anal")
def analyze():
    """Run historical pattern analysis"""
    analyze_main()

@cli.command()
@click.argument('ticker')
def ticker(ticker):
    """Analyze a specific ticker"""
    print(scan_ticker(ticker))

@cli.command(name="wipe-imports")
def wipe_imports():
    """Delete imported ticker data"""
    data_dir = os.path.join(os.path.dirname(__file__), "data", "ticker_data")
    if os.path.exists(data_dir):
        shutil.rmtree(data_dir)
        logging.info("[✔] Wiped all imported ticker data.")
    else:
        logging.info("[!] Ticker data directory not found.")

@cli.command(name="wipe-anal")
def wipe_anal():
    """Delete pattern analysis results"""
    path = os.path.join(os.path.dirname(__file__), "data", "ticker_data", "historical_pattern_analysis.csv")
    if os.path.exists(path):
        os.remove(path)
        logging.info("[✔] Wiped historical analysis results.")
    else:
        logging.info("[!] No analysis file to wipe.")

if __name__ == "__main__":
    cli()
