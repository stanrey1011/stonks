import click
import yaml
import json
import requests
from pathlib import Path
from stonkslib.utils.logging import setup_logging

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = PROJECT_ROOT / "stonkslib" / "strategies"
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
logger = setup_logging(PROJECT_ROOT / "log", "alert.log")


def _load_all_tickers():
    with open(TICKER_YAML) as f:
        data = yaml.safe_load(f)
    return [t for category in data.values() for t in category]


def _load_all_strategies():
    return [p for p in STRATEGY_DIR.glob("*.yaml")]


def _print_signals(all_signals):
    buys = [s for s in all_signals if s["type"] == "BUY"]
    sells = [s for s in all_signals if s["type"] == "SELL"]

    print(f"\n{'='*65}")
    print(f"{'ALERT SCAN RESULTS':^65}")
    print(f"{'='*65}")

    if not all_signals:
        print("  No signals fired on the latest bar.")
    else:
        if buys:
            print(f"\n  BUY signals ({len(buys)}):")
            for s in buys:
                print(f"    {s['ticker']:<8} [{s['interval']}]  ${s['close']:.2f}  {s['date']}")
                print(f"             Reason: {s['reason']}")
        if sells:
            print(f"\n  SELL signals ({len(sells)}):")
            for s in sells:
                print(f"    {s['ticker']:<8} [{s['interval']}]  ${s['close']:.2f}  {s['date']}")
                print(f"             Reason: {s['reason']}")

    print(f"\n{'='*65}\n")


def _send_discord(webhook_url, all_signals, interval):
    if not all_signals:
        return

    buys = [s for s in all_signals if s["type"] == "BUY"]
    sells = [s for s in all_signals if s["type"] == "SELL"]
    lines = [f"**Stonks Alert** — `{interval}` daily scan"]

    if buys:
        lines.append("\n**BUY signals**")
        for s in buys:
            lines.append(f"> `{s['ticker']}` ${s['close']:.2f} — {s['reason']} _(via {s.get('strategy', '?')})_")

    if sells:
        lines.append("\n**SELL signals**")
        for s in sells:
            lines.append(f"> `{s['ticker']}` ${s['close']:.2f} — {s['reason']} _(via {s.get('strategy', '?')})_")

    try:
        resp = requests.post(webhook_url, json={"content": "\n".join(lines)}, timeout=10)
        if resp.status_code == 204:
            logger.info("[✓] Discord alert sent")
        else:
            logger.warning(f"[!] Discord returned {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"[!] Discord webhook failed: {e}")


@click.command()
@click.option("--strategy", default=None,
              help="Strategy YAML filename (e.g. rsi.yaml). Omit for --all-strategies.")
@click.option("--all-strategies", "all_strategies", is_flag=True,
              help="Scan using all strategy YAMLs in stonkslib/strategies/")
@click.option("--ticker", default=None,
              help="Single ticker to check (e.g. AAPL).")
@click.option("--all-tickers", "all_tickers", is_flag=True,
              help="Check all tickers in tickers.yaml")
@click.option("--interval",
              type=click.Choice(["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]),
              default="1d", show_default=True)
@click.option("--use-optimized", "use_optimized", is_flag=True,
              help="Use optimized YAML from stonkslib/strategies/optimized/ if available")
@click.option("--webhook-url", "webhook_url", default=None, envvar="STONKS_DISCORD_WEBHOOK",
              help="Discord webhook URL to post signals to (or set STONKS_DISCORD_WEBHOOK env var)")
def alert(strategy, all_strategies, ticker, all_tickers, interval, use_optimized, webhook_url):
    """Scan latest bar for entry/exit signals across strategies and tickers.

    Examples:\n
      stonks alert --strategy rsi.yaml --ticker AAPL\n
      stonks alert --all-strategies --all-tickers --interval 1d\n
      stonks alert --strategy rsi.yaml --all-tickers --use-optimized\n
      stonks alert --strategy rsi.yaml --all-tickers --webhook-url https://discord.com/api/webhooks/...
    """
    from stonkslib.alerts.signals import check_signals

    if not strategy and not all_strategies:
        print("[!] Provide --strategy <file> or --all-strategies")
        return
    if not ticker and not all_tickers:
        print("[!] Provide --ticker <TICKER> or --all-tickers")
        return

    tickers = _load_all_tickers() if all_tickers else [ticker]

    if all_strategies:
        strategy_paths = _load_all_strategies()
    else:
        strategy_paths = [STRATEGY_DIR / strategy]

    missing = [p for p in strategy_paths if not p.exists()]
    if missing:
        for p in missing:
            print(f"[!] Strategy file not found: {p}")
        return

    all_signals = []

    for path in strategy_paths:
        if use_optimized:
            opt_path = STRATEGY_DIR / "optimized" / f"{path.stem}_optimized.yaml"
            if opt_path.exists():
                path = opt_path

        with open(path) as f:
            strat = yaml.safe_load(f)

        strat_name = strat.get("name", path.stem)
        print(f"\nStrategy: {strat_name}  ({path.name})")

        for t in tickers:
            signals = check_signals(t, interval, strat)
            if signals is None:
                logger.warning(f"[!] Skipped {t} — no data")
                continue
            if signals:
                for s in signals:
                    s["strategy"] = strat_name
                all_signals.extend(signals)
                for s in signals:
                    logger.info(f"[{s['type']}] {t} ({interval}) — {s['reason']} @ ${s['close']}")

    _print_signals(all_signals)

    if webhook_url and all_signals:
        _send_discord(webhook_url, all_signals, interval)
    elif webhook_url and not all_signals:
        logger.info("No signals — Discord not notified")
