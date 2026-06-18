import click
import yaml
from pathlib import Path

from stonkslib.utils.logging import setup_logging

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
logger = setup_logging(PROJECT_ROOT / "log", "sentiment.log")


def _resolve_tickers(target) -> list[str]:
    with open(TICKER_YAML) as f:
        wl = yaml.safe_load(f) or {}
    if not target or target.lower() == "all":
        return [t for items in wl.values() for t in (items or [])]
    for cat, items in wl.items():
        if cat.lower() == target.lower():
            return items or []
    return [target.upper()]


@click.command("sentiment-score")
@click.argument("target", required=False, default=None,
                metavar="[TICKER|CATEGORY|all]")
@click.option("--model", default=None,
              help="LLM model id (default: LLM_MODEL env / client default).")
def sentiment_score(target, model):
    """Score unscored ticker-days in the news store with the local LLM (1-10).

    For each day that has stored news but no score yet, the LLM produces a 1-10
    sentiment score, a stock-relevant summary, and a one-line reason. Idempotent —
    already-scored days are skipped, so re-runs only score new days. Run
    `stonks news-backfill` first to populate the archive.

    Examples:\n
      stonks sentiment-score NVDA\n
      stonks sentiment-score stocks --model qwen2.5:32b\n
      stonks sentiment-score all
    """
    from stonkslib.sentiment import scorer

    tickers = _resolve_tickers(target)
    if not tickers:
        print("[!] No tickers found.")
        return

    print(f"[→] Scoring news sentiment for {len(tickers)} ticker(s)…")
    total = scorer.score_pending(tickers, model=model)
    print(f"[✓] Done — {total} ticker-day(s) newly scored")
    logger.info(f"scored {total} ticker-days across {len(tickers)} tickers")
