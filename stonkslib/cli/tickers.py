import click
import yaml
import requests
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
ENV_FILE = PROJECT_ROOT / ".env"

VALID_CATEGORIES = ["stocks", "crypto", "etfs"]


def _load():
    with open(TICKER_YAML) as f:
        return yaml.safe_load(f) or {}


def _save(data):
    with open(TICKER_YAML, "w") as f:
        yaml.dump(data, f, default_flow_style=False)


def _get_webhook():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("STONKS_DISCORD_WEBHOOK="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("STONKS_DISCORD_WEBHOOK")


def _post_discord(message):
    webhook = _get_webhook()
    if not webhook:
        return
    try:
        requests.post(webhook, json={"content": message}, timeout=10)
    except Exception:
        pass


def _watchlist_message(data):
    lines = ["**Stonks Watchlist**"]
    for category, items in data.items():
        if items:
            tickers_str = "  ".join(f"`{t}`" for t in items)
            lines.append(f"**{category.capitalize()}:** {tickers_str}")
    return "\n".join(lines)


@click.group()
def tickers():
    """Manage the ticker watchlist."""


@tickers.command("list")
def list_tickers():
    """Show all tracked tickers."""
    data = _load()
    print()
    for category, items in data.items():
        print(f"  {category}:")
        for t in (items or []):
            print(f"    - {t}")
    print()


@tickers.command("add")
@click.argument("ticker")
@click.option("--category", default="stocks",
              type=click.Choice(VALID_CATEGORIES),
              show_default=True,
              help="Category to add the ticker to")
def add_ticker(ticker, category):
    """Add a ticker to the watchlist (e.g. stonks tickers add AMZN --category stocks)."""
    ticker = ticker.upper()
    data = _load()
    data.setdefault(category, [])
    if ticker in data[category]:
        print(f"[!] {ticker} already in {category}")
        return
    data[category].append(ticker)
    _save(data)
    print(f"[+] Added {ticker} to {category}")
    _post_discord(f"**Watchlist update:** `{ticker}` added to {category}\n\n{_watchlist_message(data)}")


@tickers.command("remove")
@click.argument("ticker")
def remove_ticker(ticker):
    """Remove a ticker from the watchlist."""
    ticker = ticker.upper()
    data = _load()
    removed = False
    for category, items in data.items():
        if items and ticker in items:
            items.remove(ticker)
            print(f"[-] Removed {ticker} from {category}")
            removed = True
    if not removed:
        print(f"[!] {ticker} not found in watchlist")
        return
    _save(data)
    _post_discord(f"**Watchlist update:** `{ticker}` removed\n\n{_watchlist_message(data)}")


@tickers.command("move")
@click.argument("ticker")
@click.argument("category")
def move_ticker(ticker, category):
    """Move a ticker to another category (e.g. stonks tickers move SPY etfs)."""
    ticker = ticker.upper()
    data = _load()
    found = False
    for cat, items in data.items():
        if items and ticker in items:
            items.remove(ticker)
            found = True
    if not found:
        print(f"[!] {ticker} not found in watchlist")
        return
    data.setdefault(category, [])
    if ticker not in data[category]:
        data[category].append(ticker)
    _save(data)
    print(f"[→] Moved {ticker} to {category}")


@tickers.command("announce")
def announce():
    """Post the current watchlist to Discord."""
    data = _load()
    msg = _watchlist_message(data)
    _post_discord(msg)
    print(msg)
    print("\n[✓] Posted to Discord")
