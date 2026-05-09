import click
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

@click.command()
@click.option("--output", default="output.json", help="Output file path")
@click.option("--ticker", default=None, help="Single ticker to export")
@click.option("--interval", default="1d", show_default=True)
def export(output, ticker, interval):
    """Export clean analysis data as JSON for LLM consumption."""
    from stonkslib.utils.load_td import load_td
    import yaml

    ticker_yaml = PROJECT_ROOT / "tickers.yaml"
    with open(ticker_yaml) as f:
        data = yaml.safe_load(f) or {}
    all_tickers = [t for items in data.values() for t in (items or [])]
    tickers = [ticker.upper()] if ticker else all_tickers

    td = load_td(tickers, interval)
    results = {}
    for t, df in td.items():
        if df is not None and not df.empty:
            results[t] = json.loads(df.tail(30).to_json(orient="records", date_format="iso"))

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[✓] Exported {len(results)} ticker(s) to {output_path}")
