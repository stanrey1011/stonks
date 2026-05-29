"""
Robinhood positions/account via the SnapTrade aggregator (read-only).

Robinhood has no official API; holdings are read through SnapTrade. See
`stonkslib/broker/snaptrade.py` for the signed REST client and the one-time
connection-portal flow. This module adapts SnapTrade's Robinhood account(s) to the
canonical broker schema the dashboard renders.

Read-only: SnapTrade + Robinhood is data-only (no order placement). Robinhood only
syncs *holdings* through SnapTrade (not transactions), so `get_orders()` may be
empty. Both the "Robinhood Individual" and "Robinhood Crypto" accounts are merged.

For the dashboard, prefer `get_snapshot()` — it fetches everything in a single pass
(one accounts lookup; positions/balances/orders fetched once each), instead of the
redundant calls you'd get from `get_account` + `get_positions` + `get_orders`
separately. SnapTrade only syncs holdings ~daily, so callers should cache the result.
"""
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from stonkslib.broker import snaptrade

_INSTITUTION = "Robinhood"


def is_configured() -> bool:
    """SnapTrade partner keys present in .env."""
    return snaptrade.is_configured()


def is_connected() -> bool:
    """A Robinhood account has been linked through the SnapTrade portal."""
    if not is_configured() or snaptrade._load_user() is None:
        return False
    try:
        return len(snaptrade.find_accounts(_INSTITUTION)) > 0
    except Exception:
        return False


def connect_url() -> str:
    """Generate a SnapTrade Connection Portal URL to (re)link Robinhood."""
    return snaptrade.connection_portal_url(connection_type="read")


# ── helpers ─────────────────────────────────────────────────────────────────────

def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _ticker(pos: dict) -> str:
    """Positions nest the ticker at position['symbol']['symbol']['symbol']."""
    sym = pos.get("symbol") or {}
    inner = sym.get("symbol") if isinstance(sym, dict) else None
    if isinstance(inner, dict):
        return inner.get("symbol") or inner.get("raw_symbol") or inner.get("description") or ""
    if isinstance(inner, str):
        return inner
    return ""


def _order_ticker(o: dict) -> str:
    """Orders nest the ticker under universal_symbol.symbol (options under option_symbol)."""
    us = o.get("universal_symbol")
    if isinstance(us, dict) and us.get("symbol"):
        return us["symbol"]
    opt = o.get("option_symbol")
    if isinstance(opt, dict):
        return opt.get("ticker") or opt.get("raw_symbol") or ""
    return ""


def _position_row(p: dict) -> dict:
    units = _f(p.get("units") or p.get("fractional_units"))
    price = _f(p.get("price"))
    avg   = _f(p.get("average_purchase_price"))
    pnl   = _f(p.get("open_pnl"))
    cost  = units * avg
    return {
        "symbol":             _ticker(p),
        "qty":                units,
        "avg_cost":           avg,
        "market_value":       units * price,
        "unrealized_pnl":     pnl,
        "unrealized_pnl_pct": (pnl / cost * 100) if cost else 0.0,
    }


def _order_row(o: dict) -> dict:
    return {
        "symbol":     _order_ticker(o),
        "side":       o.get("action") or o.get("side", ""),
        "qty":        _f(o.get("total_quantity") or o.get("filled_quantity")),
        "filled_qty": _f(o.get("filled_quantity")),
        "type":       o.get("order_type", ""),
        "status":     o.get("status", ""),
        "submitted":  str(o.get("time_placed") or o.get("time_executed") or "")[:16],
        "filled_avg": _f(o.get("execution_price")),
    }


def _robinhood_accounts() -> list[dict]:
    return snaptrade.find_accounts(_INSTITUTION)


# ── single-pass snapshot (preferred for the dashboard) ──────────────────────────

def _safe_orders(account_id: str) -> list[dict]:
    try:
        return snaptrade.account_orders(account_id) or []
    except Exception:
        return []


def get_snapshot(order_limit: int = 25) -> dict:
    """Fetch account + positions + orders in one pass across all linked Robinhood
    accounts. Returns {connected, account, positions (DataFrame), orders (DataFrame)}.
    Cash may be negative (margin), so equity = holdings value + cash.

    The per-account positions/balances/orders calls are fired concurrently — each
    SnapTrade GET is slow (~3s), so parallelizing turns ~7 sequential calls into a
    couple of waves. Callers should still cache the result (data is ~daily fresh)."""
    accounts = _robinhood_accounts()
    aids = [a["id"] for a in accounts]
    empty = {
        "connected": False,
        "account": {"portfolio_value": 0.0, "equity": 0.0, "cash": 0.0, "buying_power": 0.0},
        "positions": pd.DataFrame(),
        "orders": pd.DataFrame(),
    }
    if not aids:
        return empty

    with ThreadPoolExecutor(max_workers=min(len(aids) * 3, 12)) as ex:
        pos_futs = {aid: ex.submit(snaptrade.account_positions, aid) for aid in aids}
        bal_futs = {aid: ex.submit(snaptrade.account_balances, aid) for aid in aids}
        ord_futs = {aid: ex.submit(_safe_orders, aid) for aid in aids}

    pos_rows: list[dict] = []
    ord_rows: list[dict] = []
    cash = buying_power = holdings = 0.0
    for aid in aids:
        for p in pos_futs[aid].result():
            pos_rows.append(_position_row(p))
            holdings += _f(p.get("units") or p.get("fractional_units")) * _f(p.get("price"))
        for b in bal_futs[aid].result():
            cash         += _f(b.get("cash"))
            buying_power += _f(b.get("buying_power"))
        ord_rows.extend(_order_row(o) for o in ord_futs[aid].result()[:order_limit])

    equity = holdings + cash
    return {
        "connected": True,
        "account": {
            "portfolio_value": equity,
            "equity":          equity,
            "cash":            cash,
            "buying_power":    buying_power,
        },
        "positions": pd.DataFrame(pos_rows),
        "orders":    pd.DataFrame(ord_rows),
    }


# ── canonical broker surface (used by Home badge / other callers) ───────────────

def get_positions() -> pd.DataFrame:
    rows = []
    for acct in _robinhood_accounts():
        rows.extend(_position_row(p) for p in snaptrade.account_positions(acct["id"]))
    return pd.DataFrame(rows)


def get_account() -> dict:
    cash = buying_power = holdings = 0.0
    for acct in _robinhood_accounts():
        for b in snaptrade.account_balances(acct["id"]):
            cash         += _f(b.get("cash"))
            buying_power += _f(b.get("buying_power"))
        for p in snaptrade.account_positions(acct["id"]):
            holdings += _f(p.get("units") or p.get("fractional_units")) * _f(p.get("price"))
    equity = holdings + cash
    return {
        "portfolio_value": equity,
        "equity":          equity,
        "cash":            cash,
        "buying_power":    buying_power,
    }


def get_orders(limit: int = 25) -> pd.DataFrame:
    rows = []
    for acct in _robinhood_accounts():
        try:
            orders = snaptrade.account_orders(acct["id"]) or []
        except Exception:
            orders = []
        rows.extend(_order_row(o) for o in orders[:limit])
    return pd.DataFrame(rows)
