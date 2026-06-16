import os
from datetime import date

import requests

NOTIFY_URL = os.getenv("NOTIFY_URL", "http://localhost:8600")


def send(message: str) -> None:
    """POST a message to the notify service. Fails silently — alerts are best-effort."""
    try:
        requests.post(
            f"{NOTIFY_URL}/send",
            json={"message": message, "app": "stonks"},
            timeout=5,
        )
    except Exception:
        pass


def format_alert_sms(all_signals: list) -> str | None:
    if not all_signals:
        return None
    buys  = [s for s in all_signals if s["type"] == "BUY"]
    sells = [s for s in all_signals if s["type"] == "SELL"]
    today = date.today().strftime("%m-%d")
    lines = [f"stonks {today}  BUY:{len(buys)} SELL:{len(sells)}"]
    for s in buys:
        lines.append(f"BUY  {s['ticker']:<6} ${s['close']:.0f} [{s['interval']}]")
    for s in sells:
        lines.append(f"SELL {s['ticker']:<6} ${s['close']:.0f} [{s['interval']}]")
    return "\n".join(lines)


def format_leaps_sms(results: list, vix_current, vix_rank) -> str | None:
    if not results:
        return None
    today   = date.today().strftime("%m-%d")
    vix_str = f"VIX {vix_current:.1f} ({vix_rank:.0f}%)" if vix_current else "VIX n/a"
    lines   = [f"stonks LEAPs {today}  {vix_str}"]
    for r in results:
        lines.append(f"{r['direction']:<4} {r['ticker']:<6} ${r['current_price']:.0f}  [{r['signal_count']} sig]")
    return "\n".join(lines)
