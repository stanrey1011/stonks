import click
import yaml
import requests
from pathlib import Path
from stonkslib.utils.logging import setup_logging

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = PROJECT_ROOT / "stonkslib" / "strategies"
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
logger = setup_logging(PROJECT_ROOT / "log", "alert.log")


def _resolve_tickers(target):
    with open(TICKER_YAML) as f:
        data = yaml.safe_load(f) or {}
    if not target or target.lower() == "all":
        return [t for items in data.values() for t in (items or [])]
    for cat, tickers in data.items():
        if cat.lower() == target.lower():
            return tickers or []
    return [target.upper()]


def _load_all_strategies():
    return list(STRATEGY_DIR.glob("*.yaml"))


def _resolve_strategy_path(path):
    """Return optimized version of a strategy if it exists, else original."""
    opt_path = STRATEGY_DIR / "optimized" / f"{path.stem}_optimized.yaml"
    return opt_path if opt_path.exists() else path


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
@click.argument("target", required=False, default=None,
                metavar="[TICKER|CATEGORY|all]")
@click.option("--strategy", default=None,
              help="Strategy YAML filename (e.g. rsi.yaml). Omit for --all-strategies.")
@click.option("--all-strategies", "all_strategies", is_flag=True,
              help="Scan using all strategy YAMLs")
@click.option("--interval",
              type=click.Choice(["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]),
              default="1d", show_default=True)
@click.option("--webhook-url", "webhook_url", default=None, envvar="STONKS_DISCORD_WEBHOOK",
              help="Discord webhook URL (or set STONKS_DISCORD_WEBHOOK env var)")
def alert(target, strategy, all_strategies, interval, webhook_url):
    """Scan latest bar for entry/exit signals. Auto-uses optimized strategies when available.

    TARGET can be a ticker (AAPL), a category (stocks/etfs/crypto), or 'all'.\n

    Examples:\n
      stonks alert AAPL --strategy rsi.yaml\n
      stonks alert all --all-strategies --interval 1d\n
      stonks alert crypto --all-strategies --interval 1wk
    """
    from stonkslib.alerts.signals import check_signals

    if not target:
        print("[!] Provide a ticker (AAPL), category (stocks/etfs/crypto), or 'all'")
        return
    if not strategy and not all_strategies:
        print("[!] Provide --strategy <file> or --all-strategies")
        return

    tickers = _resolve_tickers(target)

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
        resolved = _resolve_strategy_path(path)
        if resolved != path:
            logger.info(f"[opt] Using optimized: {resolved.name}")

        with open(resolved) as f:
            strat = yaml.safe_load(f)

        strat_name = strat.get("name", path.stem)
        print(f"\nStrategy: {strat_name}  ({resolved.name})")

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
