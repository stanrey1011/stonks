import click
import yaml
from pathlib import Path
from stonkslib.utils.logging import setup_logging

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
logger = setup_logging(PROJECT_ROOT / "log", "leaps.log")


def _resolve_tickers(target):
    with open(TICKER_YAML) as f:
        data = yaml.safe_load(f) or {}
    if not target or target.lower() == "all":
        return [t for items in data.values() for t in (items or [])]
    for cat, tickers in data.items():
        if cat.lower() == target.lower():
            return tickers or []
    return [target.upper()]


def _vix_label(vix_rank):
    if vix_rank is None:
        return "unknown"
    if vix_rank < 25:
        return "LOW — good environment to buy"
    if vix_rank < 60:
        return "MODERATE"
    return "HIGH — options expensive"


def _print_results(results, vix_current, vix_rank):
    width = 72
    print(f"\n{'='*width}")
    print(f"{'LEAP OPPORTUNITIES':^{width}}")
    print(f"{'='*width}")

    if vix_current:
        print(f"  VIX {vix_current:.2f}  |  52-week rank: {vix_rank:.0f}%  |  {_vix_label(vix_rank)}")
    else:
        print("  VIX: unavailable")

    print(f"{'='*width}")

    if not results:
        print("  No signals found across watchlist.")
        print(f"{'='*width}\n")
        return

    calls = [r for r in results if r["direction"] == "CALL"]
    puts  = [r for r in results if r["direction"] == "PUT"]

    for label, group in [("CALL candidates  (bullish)", calls), ("PUT candidates  (hedge / bearish)", puts)]:
        if not group:
            continue
        print(f"\n  {label}")
        print(f"  {'-'*68}")
        for r in group:
            vix_note = "  ⚠ single stock — VIX is approximate" if r["category"] == "stocks" else ""
            print(f"  {r['ticker']:<8} ${r['current_price']:>8.2f}  [{r['signal_count']} signal(s)]  {r['category']}{vix_note}")
            for reason in r["top_reasons"]:
                print(f"             • {reason}")

            opt = r.get("option")
            if opt:
                bid_ask = f"${opt['bid']:.2f} / ${opt['ask']:.2f}" if opt["bid"] and opt["ask"] else "n/a"
                iv_str  = f"  IV {opt['iv']}%" if opt["iv"] else ""
                oi_str  = f"  OI {opt['open_interest']}" if opt["open_interest"] else ""
                print(f"             → {r['direction']} ${opt['strike']:.0f}  exp {opt['expiry']}  {bid_ask}{iv_str}{oi_str}")
            elif r["category"] == "crypto":
                print(f"             → No standard options available (crypto)")
            else:
                print(f"             → Options chain unavailable")

    print(f"\n{'='*width}\n")


@click.command()
@click.argument("target", required=False, default=None, metavar="[TICKER|CATEGORY|all]")
@click.option("--interval", type=click.Choice(["1d", "1wk"]), default="1wk", show_default=True,
              help="Price interval for signal detection (1wk recommended for LEAPs)")
def leaps(target, interval):
    """Scan for LEAP call/put opportunities using VIX rank + technical signals.

    Aggregates signals from all strategies. VIX rank is used as a market-wide
    IV proxy — most reliable for ETFs, approximate for individual stocks.
    Low VIX rank = cheaper options environment.

    Examples:\n
      stonks leaps all\n
      stonks leaps etfs\n
      stonks leaps AAPL\n
      stonks leaps stocks --interval 1d
    """
    from stonkslib.leaps.scanner import scan_leaps

    if not target:
        print("[!] Provide a ticker, category (stocks/etfs/crypto), or 'all'")
        return

    tickers = _resolve_tickers(target)
    print(f"\nScanning {len(tickers)} ticker(s) on {interval}...")

    results, vix_current, vix_rank = scan_leaps(tickers, interval)
    _print_results(results, vix_current, vix_rank)

    from stonkslib import notify
    msg = notify.format_leaps_sms(results, vix_current, vix_rank)
    if msg:
        notify.send(msg)
