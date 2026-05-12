import re
import json
import click
import pandas as pd
from pathlib import Path
from stonkslib.utils.logging import setup_logging

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEAPS_DIR = PROJECT_ROOT / "data" / "backtest_results" / "leaps"
logger = setup_logging(PROJECT_ROOT / "log", "leaps.log")


def _find_csv(ticker, interval, option_type, keyword):
    base = LEAPS_DIR / ticker.upper() / interval
    if not base.exists():
        return None, None

    # Filter by option_type suffix
    candidates = [f for f in base.glob(f"*_{option_type}.csv")]
    if not candidates:
        candidates = list(base.glob("*.csv"))

    if keyword:
        slug = re.sub(r"[^a-z0-9]+", "_", keyword.lower()).strip("_")
        matched = [f for f in candidates if slug in f.stem or keyword.replace(" ", "") in f.stem]
        if not matched:
            words = keyword.lower().split()
            matched = [f for f in candidates if any(w in f.stem for w in words)]
    else:
        matched = candidates

    if not matched:
        return None, candidates

    if len(matched) > 1:
        # Pick best by net_pnl from metrics JSON
        best, best_pnl = None, float("-inf")
        for f in matched:
            mf = f.with_name(f.stem + "_metrics.json")
            if mf.exists():
                m = json.loads(mf.read_text())
                if m.get("net_pnl", float("-inf")) > best_pnl:
                    best_pnl, best = m["net_pnl"], f
        matched = [best] if best else [matched[0]]

    return matched[0], candidates


def _weeks_held(entry_date, exit_date):
    try:
        e = pd.to_datetime(entry_date, utc=True)
        x = pd.to_datetime(exit_date, utc=True)
        return max(1, round((x - e).days / 7))
    except Exception:
        return "?"


def print_leaps_trades(ticker, interval, option_type, keyword, file=None):
    """Print the LEAP trade log. Returns True if output was produced."""
    csv_path, candidates = _find_csv(ticker, interval, option_type, keyword)

    if csv_path is None:
        if candidates is None:
            print(f"[!] No LEAP backtest data for {ticker} ({interval}). Run `stonks leaps-backtest {ticker}` first.")
        elif candidates:
            names = ", ".join(f"`{c.stem}`" for c in sorted(candidates))
            print(f"[!] No match for '{keyword}'. Available: {names}")
        else:
            print(f"[!] No LEAP trades found for {ticker} ({interval} · {option_type}).")
        return False

    df = pd.read_csv(csv_path)
    if df.empty:
        print(f"No trades recorded in {csv_path.name}.")
        return False

    # Load metrics for header
    mf = csv_path.with_name(csv_path.stem + "_metrics.json")
    metrics = json.loads(mf.read_text()) if mf.exists() else {}

    strategy_label = csv_path.stem.replace("_call", "").replace("_put", "").replace("_auto", "").replace("_", " ").title()
    otype = option_type.upper()

    buys  = df[df["action"] == "BUY_LEAP"].reset_index(drop=True)
    sells = df[df["action"].isin(["SELL_LEAP", "SELL_LEAP_END"])].reset_index(drop=True)

    width = 100
    print(f"\n{'='*width}")
    print(f"  LEAP Trade Log — {ticker.upper()}  ·  {otype}  ·  {strategy_label}  ·  {interval}")
    if metrics:
        print(f"  Net P&L: ${metrics.get('net_pnl', 0):,.2f}  |  "
              f"Trades: {metrics.get('trades', 0)}  |  "
              f"Win rate: {metrics.get('win_rate', 0):.1%}  |  "
              f"Avg trade: {metrics.get('avg_pnl_pct', 0):.1f}%")
    print(f"{'='*width}")
    print(f"  {'#':<4} {'Entry':<12} {'Spot':>7} {'Strike':>7} {'Prem':>6} {'Qty':>4}  "
          f"{'Exit':<12} {'Spot':>7} {'Prem':>6} {'P&L':>10} {'%':>7}  {'Held':>5}  Reason")
    print(f"  {'-'*96}")

    for i in range(len(buys)):
        b = buys.iloc[i]
        entry_date = str(b["date"])[:10]
        spot_in    = f"${b['spot']:.2f}"
        strike     = f"${b['strike']:.2f}"
        prem_in    = f"${b['premium']:.2f}"
        qty        = int(b["contracts"])

        if i < len(sells):
            s = sells.iloc[i]
            exit_date  = str(s["date"])[:10]
            spot_out   = f"${s['spot']:.2f}"
            prem_out   = f"${s['premium']:.2f}"
            pnl        = s.get("pnl", 0)
            pnl_pct    = s.get("pnl_pct", 0)
            pnl_str    = f"+${pnl:,.2f}" if pnl >= 0 else f"-${abs(pnl):,.2f}"
            pct_str    = f"+{pnl_pct:.1f}%" if pnl_pct >= 0 else f"{pnl_pct:.1f}%"
            held       = f"{_weeks_held(b['date'], s['date'])}wk"
            reason     = str(s.get("reason", ""))[:22]
            marker     = "✓" if pnl >= 0 else "✗"
            print(f"  {i+1:<4} {entry_date:<12} {spot_in:>7} {strike:>7} {prem_in:>6} {qty:>4}  "
                  f"{exit_date:<12} {spot_out:>7} {prem_out:>6} {pnl_str:>10} {pct_str:>7}  {held:>5}  {reason} {marker}")
        else:
            print(f"  {i+1:<4} {entry_date:<12} {spot_in:>7} {strike:>7} {prem_in:>6} {qty:>4}  "
                  f"{'open':<12} {'—':>7} {'—':>6} {'—':>10} {'—':>7}  {'—':>5}")

    print(f"{'='*width}\n")
    return True


@click.command("leaps-trades")
@click.argument("ticker")
@click.option("--interval", type=click.Choice(["1d", "1wk"]), default="1wk", show_default=True)
@click.option("--option-type", "option_type",
              type=click.Choice(["call", "put", "auto"]), default="call", show_default=True)
@click.option("--strategy", default=None,
              help="Strategy keyword to match (e.g. 'supertrend', 'rsi macd', 'ma crossover'). "
                   "Omit to use the best-performing strategy.")
def leaps_trades(ticker, interval, option_type, strategy):
    """Show entry/exit dates for a LEAP backtest trade log.

    Run `stonks leaps-backtest TICKER` first to generate the data.

    Examples:\n
      stonks leaps-trades NVDA\n
      stonks leaps-trades NVDA --option-type call --strategy supertrend\n
      stonks leaps-trades QBTS --option-type put --strategy rsi macd\n
      stonks leaps-trades AMD --interval 1wk --option-type call
    """
    print_leaps_trades(ticker, interval, option_type, strategy)
