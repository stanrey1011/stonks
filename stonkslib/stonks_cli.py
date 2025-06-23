import os
import click
import yaml

from stonkslib.fetch.ranges import fetch_all
from stonkslib.utils.load_td import load_td
#from stonkslib.patterns.find_patterns import find_patterns
from stonkslib.alerts.trade_alerts import trigger_alerts  # Optional, if using alerts

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TICKER_YAML = os.path.join(BASE_DIR, "tickers.yaml")

def load_tickers(yaml_file=TICKER_YAML):
    with open(yaml_file, "r") as f:
        data = yaml.safe_load(f)
    return data['stocks'] + data['crypto'] + data['etfs']

@click.group()
def cli():
    """Stonks CLI"""
    pass

@cli.command(name="fetch")
@click.option("--force", is_flag=True, help="Force re-download and overwrite existing CSVs")
def fetch_cmd(force):
    """Fetch all data for all tickers with predefined intervals"""
    fetch_all(force=force)

@cli.command(name="anal")
def anal_cmd():
    """Analyze historical patterns and print alerts"""
    tickers = load_tickers()
    intervals = ["1d", "1wk"]
    alerts = []

    for ticker in tickers:
        for interval in intervals:
            data = load_ticker_data(ticker, base_dir="data/ticker_data", interval=interval)
            if data is not None and not data.empty:
                patterns = find_patterns(data, [interval])
                for p in patterns:
                    alerts.append(f"Alert for {ticker} ({interval}): {p['pattern_type']} detected!")

    if alerts:
        for alert in alerts:
            print(alert)
    else:
        print("No patterns detected.")
