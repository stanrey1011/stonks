import click
import json
from pathlib import Path
from stonkslib.cli.analyze import stocks, options
from stonkslib.cli.clean import load_tickers

@click.command()
@click.option('--output', default='output.json', help='Output file for LLM')
@click.option('--data-type', type=click.Choice(['stocks', 'options']), default='stocks')
@click.option('--strategy', default=None, help='Strategy for options analysis')
@click.option('--side', type=click.Choice(['buy', 'sell']), default=None, help='Buy or sell side for options')
@click.option('--option_type', type=click.Choice(['calls', 'puts']), default=None, help='Option type for options')
def export(output, data_type, strategy, side, option_type):
    """Export analysis results as JSON for LLM."""
    results = []
    if data_type == 'stocks':
        results = stocks.callback(ticker=None, interval='1d')
    else:
        results = options.callback(ticker=None, strategy=strategy, side=side, option_type=option_type)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"[✓] Exported {data_type} analysis to {output_path}")