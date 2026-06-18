import click
import yaml
from pathlib import Path

from stonkslib.utils.logging import setup_logging

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
logger = setup_logging(PROJECT_ROOT / "log", "news.log")


def _resolve_tickers(target) -> list[str]:
    with open(TICKER_YAML) as f:
        wl = yaml.safe_load(f) or {}
    if not target or target.lower() == "all":
        return [t for items in wl.values() for t in (items or [])]
    for cat, items in wl.items():
        if cat.lower() == target.lower():
            return items or []
    return [target.upper()]


@click.command("news-backfill")
@click.argument("target", required=False, default=None,
                metavar="[TICKER|CATEGORY|all]")
@click.option("--days", default=365, show_default=True,
              help="How many days of history to fetch (Finnhub free tier ≈ 1 year).")
def news_backfill(target, days):
    """Backfill Finnhub company-news into the historical news store (SQLite).

    Articles are upserted by id, so re-runs are idempotent and just top up the
    archive. Feeds `stonks sentiment-score`.

    Examples:\n
      stonks news-backfill NVDA\n
      stonks news-backfill stocks --days 730\n
      stonks news-backfill all
    """
    from stonkslib.utils import news_store

    tickers = _resolve_tickers(target)
    if not tickers:
        print("[!] No tickers found.")
        return

    print(f"[→] Backfilling news for {len(tickers)} ticker(s), last {days} days…")
    total = 0
    for ticker in tickers:
        try:
            n = news_store.backfill(ticker, days=days)
            total += n
            print(f"  [✓] {ticker}: {n} articles")
            logger.info(f"[✓] {ticker}: {n} articles")
        except Exception as e:
            print(f"  [!] {ticker}: {e}")
            logger.error(f"[!] {ticker}: {e}")
    print(f"[✓] Done — {total} articles into {news_store.DB_PATH}")
