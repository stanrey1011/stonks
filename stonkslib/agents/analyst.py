"""Analyst brief — a thin view over the unified snapshot (`stonkslib/snapshot.py`).

`analyst_brief(ticker)` reshapes one `TickerSnapshot` into the dict the Analyst
dashboard page renders. It used to gather from ~7 sources directly; that gather
now lives in `snapshot.hydrate()` (one source of truth, shared by the dashboard,
the multi-agent fund, and the CLI). This module just renames a few fields for the
page's existing layout — keep it that way; new data belongs in `hydrate()`.
"""

from stonkslib.snapshot import hydrate


def analyst_brief(ticker: str, interval: str = "1d", news_days: int = 7) -> dict:
    """Assemble the analyst brief for a ticker, as a view over `hydrate()`."""
    snap = hydrate(ticker, interval=interval, news_days=news_days)

    # The page calls the confluence pane "ta"; map it across (preserve errors).
    conf = snap.get("confluence") or {}
    if "error" in conf:
        ta = {"error": conf["error"]}
    else:
        ta = {
            "votes": conf.get("votes", []),
            "readouts": conf.get("readouts", {}),
            "buy_score": conf.get("buy_score", 0.0),
            "sell_score": conf.get("sell_score", 0.0),
            "asof": conf.get("asof"),
        }

    return {
        "ticker": snap.get("ticker"),
        "interval": snap.get("interval"),
        "fundamentals": snap.get("fundamentals") or {},
        "earnings": snap.get("earnings") or {},
        "dividends": snap.get("dividends") or {},
        "sentiment": snap.get("sentiment") or {},
        "news": snap.get("news") or {},
        "ta": ta,
    }
