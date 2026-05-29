import click
import yaml
from pathlib import Path
from stonkslib.utils.logging import setup_logging

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
logger = setup_logging(PROJECT_ROOT / "log", "earnings.log")


def _all_tickers() -> list[str]:
    with open(TICKER_YAML) as f:
        data = yaml.safe_load(f) or {}
    return [t for items in data.values() for t in (items or [])]


def _has_earnings(ticker: str) -> bool:
    """Skip crypto and tickers with no earnings reports."""
    return not (ticker.endswith("-USD") or ticker.endswith("-USDT"))


@click.command("earnings-refresh")
@click.argument("target", required=False, default=None,
                metavar="[TICKER|CATEGORY|all]")
def earnings_refresh(target):
    """Refresh the earnings cache for watchlist tickers.

    Fetches from yfinance (deep history) + Finnhub (recent quarters + upcoming date)
    and saves to data/ticker_data/earnings/. Safe to run any day — crypto and
    ETFs without earnings are skipped automatically.

    Examples:\n
      stonks earnings-refresh\n
      stonks earnings-refresh NVDA\n
      stonks earnings-refresh stocks
    """
    from stonkslib.utils.earnings import fetch_and_save

    with open(TICKER_YAML) as f:
        wl = yaml.safe_load(f) or {}

    if not target or target.lower() == "all":
        tickers = [t for items in wl.values() for t in (items or [])]
    else:
        matched = False
        for cat, items in wl.items():
            if cat.lower() == target.lower():
                tickers = items or []
                matched = True
                break
        if not matched:
            tickers = [target.upper()]

    tickers = [t for t in tickers if _has_earnings(t)]

    if not tickers:
        print("[!] No eligible tickers found.")
        return

    from stonkslib.utils.dividends import fetch_and_save as div_fetch

    print(f"[→] Refreshing earnings + dividends for {len(tickers)} ticker(s)...")
    ok = 0
    for ticker in tickers:
        try:
            data = fetch_and_save(ticker)
            n = len(data.get("history", []))
            next_d = data.get("next_date") or "—"
            print(f"  [✓] {ticker} earnings: {n} entries, next={next_d}")
            logger.info(f"[✓] {ticker}: {n} entries, next={next_d}")
            ok += 1
        except Exception as e:
            print(f"  [!] {ticker} earnings: {e}")
            logger.error(f"[!] {ticker}: {e}")

        try:
            div = div_fetch(ticker)
            yld = f"{div['dividend_yield']*100:.2f}%" if div.get("dividend_yield") else "—"
            print(f"  [✓] {ticker} dividends: yield={yld}, ex={div.get('ex_date') or '—'}")
        except Exception as e:
            print(f"  [!] {ticker} dividends: {e}")

    print(f"[✓] Done — {ok}/{len(tickers)} refreshed")
