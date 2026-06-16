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
import math
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


def _symbol_obj(pos: dict) -> dict:
    """The universal-symbol dict nested at position['symbol']['symbol']."""
    sym = pos.get("symbol") or {}
    inner = sym.get("symbol") if isinstance(sym, dict) else None
    return inner if isinstance(inner, dict) else {}


def _ticker(pos: dict) -> str:
    """Positions nest the ticker at position['symbol']['symbol']['symbol']."""
    sym = pos.get("symbol") or {}
    inner = sym.get("symbol") if isinstance(sym, dict) else None
    if isinstance(inner, dict):
        return inner.get("symbol") or inner.get("raw_symbol") or inner.get("description") or ""
    if isinstance(inner, str):
        return inner
    return ""


def _is_crypto_position(pos: dict, account_name: str = "") -> bool:
    """Classify an equity-endpoint position as crypto vs stock/ETF. SnapTrade tags
    the security type on the universal symbol (`type.code`/`type.description`);
    fall back to the account name (Robinhood exposes a separate 'Crypto' account)."""
    t = _symbol_obj(pos).get("type") or {}
    blob = f"{t.get('code', '')} {t.get('description', '')}".lower()
    if "crypto" in blob:
        return True
    return "crypto" in account_name.lower()


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


def _option_row(o: dict) -> dict:
    """Adapt a SnapTrade option holding to a per-contract row. The contract nests
    under symbol.option_symbol. NOTE: SnapTrade's `price` is already the per-contract
    market value (units * price == position value, verified against the broker-
    reported account total) — do NOT apply a 100x multiplier. Robinhood doesn't
    expose option cost basis through SnapTrade (`average_purchase_price` is null), so
    avg cost and P&L are left blank (NaN) rather than fabricated from a zero cost."""
    sym   = o.get("symbol") or {}
    opt   = sym.get("option_symbol") or {}
    under = opt.get("underlying_symbol") or {}
    units = _f(o.get("units"))
    price = _f(o.get("price"))
    mkt   = units * price
    has_avg = o.get("average_purchase_price") is not None
    avg   = _f(o.get("average_purchase_price")) if has_avg else math.nan
    cost  = units * avg
    if o.get("open_pnl") is not None:
        pnl = _f(o.get("open_pnl"))
    elif has_avg:
        pnl = mkt - cost
    else:
        pnl = math.nan
    return {
        "symbol":             under.get("symbol") or opt.get("ticker") or sym.get("description", ""),
        "contract":           opt.get("ticker") or sym.get("description", ""),
        "type":               str(opt.get("option_type") or "").upper(),
        "strike":             _f(opt.get("strike_price")),
        "expiry":             str(opt.get("expiration_date") or "")[:10],
        "qty":                units,
        "avg_cost":           avg,
        "market_value":       mkt,
        "unrealized_pnl":     pnl,
        "unrealized_pnl_pct": (pnl / cost * 100) if (has_avg and cost) else math.nan,
    }


def _account_summary(a: dict) -> dict:
    """Pull the useful identity/freshness fields off a SnapTrade account object.
    `number` is masked to the last 4. `last_sync` reflects the holdings sync — RH
    syncs ~daily, so this tells the user how stale the snapshot is."""
    num = str(a.get("number") or "")
    bal = (a.get("balance") or {}).get("total") or {}
    sync = ((a.get("sync_status") or {}).get("holdings") or {})
    return {
        "name":        a.get("name") or a.get("institution_name") or "Robinhood",
        "number":      f"••••{num[-4:]}" if len(num) >= 4 else (num or "—"),
        "total_value": _f(bal.get("amount")),
        "currency":    (bal.get("currency") or {}).get("code", "USD") if isinstance(bal.get("currency"), dict) else (bal.get("currency") or "USD"),
        "last_sync":   sync.get("last_successful_sync") or "",
    }


def _robinhood_accounts() -> list[dict]:
    return snaptrade.find_accounts(_INSTITUTION)


# ── single-pass snapshot (preferred for the dashboard) ──────────────────────────

def _safe_orders(account_id: str) -> list[dict]:
    try:
        return snaptrade.account_orders(account_id) or []
    except Exception:
        return []


def _safe_options(account_id: str) -> list[dict]:
    try:
        return snaptrade.account_options(account_id) or []
    except Exception:
        return []


def _safe_return_rates(account_id: str):
    try:
        return snaptrade.account_return_rates(account_id)
    except Exception as e:
        return {"_error": str(e)[:200]}


def _safe_activities(account_id: str) -> list[dict]:
    try:
        return snaptrade.account_activities(account_id) or []
    except Exception:
        return []


def get_snapshot(order_limit: int = 25) -> dict:
    """Fetch account + positions + options + orders in one pass across all linked
    Robinhood accounts. Returns a dict with the account summary plus DataFrames split
    by asset class: `stocks`, `crypto`, `options`, a combined `positions` (stocks +
    crypto), and `orders`. `debug` carries the raw account list and option payload so
    the dashboard can show whether SnapTrade actually syncs Robinhood options.
    Cash may be negative (margin), so equity = holdings value + cash.

    The per-account positions/options/balances/orders calls are fired concurrently —
    each SnapTrade GET is slow (~3s), so parallelizing turns the sequential calls into
    a couple of waves. Callers should still cache the result (data is ~daily fresh)."""
    accounts = _robinhood_accounts()
    acct_by_id = {a["id"]: a for a in accounts}
    aids = list(acct_by_id)
    empty = {
        "connected": False,
        "account": {"portfolio_value": 0.0, "equity": 0.0, "cash": 0.0, "buying_power": 0.0},
        "accounts": [],
        "stocks": pd.DataFrame(),
        "crypto": pd.DataFrame(),
        "options": pd.DataFrame(),
        "positions": pd.DataFrame(),
        "orders": pd.DataFrame(),
        "debug": {"accounts": [], "raw_options": {}, "raw_return_rates": {},
                  "raw_activities": {}, "counts": {}},
    }
    if not aids:
        return empty

    with ThreadPoolExecutor(max_workers=min(len(aids) * 6, 24)) as ex:
        pos_futs = {aid: ex.submit(snaptrade.account_positions, aid) for aid in aids}
        opt_futs = {aid: ex.submit(_safe_options, aid) for aid in aids}
        bal_futs = {aid: ex.submit(snaptrade.account_balances, aid) for aid in aids}
        ord_futs = {aid: ex.submit(_safe_orders, aid) for aid in aids}
        ret_futs = {aid: ex.submit(_safe_return_rates, aid) for aid in aids}
        act_futs = {aid: ex.submit(_safe_activities, aid) for aid in aids}

    stock_rows: list[dict] = []
    crypto_rows: list[dict] = []
    option_rows: list[dict] = []
    ord_rows: list[dict] = []
    raw_options: dict = {}
    raw_returns: dict = {}
    raw_activities: dict = {}
    cash = buying_power = holdings = 0.0
    for aid in aids:
        acct = acct_by_id[aid]
        acct_name = f"{acct.get('institution_name', '')} {acct.get('name', '')}"
        for p in pos_futs[aid].result():
            (crypto_rows if _is_crypto_position(p, acct_name) else stock_rows).append(_position_row(p))
            holdings += _f(p.get("units") or p.get("fractional_units")) * _f(p.get("price"))
        opts = opt_futs[aid].result()
        raw_options[aid] = opts
        for o in opts:
            row = _option_row(o)
            option_rows.append(row)
            holdings += row["market_value"]
        for b in bal_futs[aid].result():
            cash         += _f(b.get("cash"))
            buying_power += _f(b.get("buying_power"))
        ord_rows.extend(_order_row(o) for o in ord_futs[aid].result()[:order_limit])
        raw_returns[aid] = ret_futs[aid].result()
        raw_activities[aid] = act_futs[aid].result()

    equity = holdings + cash
    # Options from Robinhood lack a cost basis (NaN P&L) — exclude them from the
    # rollup so they don't poison the sum; their value still counts toward holdings.
    total_pnl = sum(
        r["unrealized_pnl"] for r in (*stock_rows, *crypto_rows, *option_rows)
        if not (isinstance(r["unrealized_pnl"], float) and math.isnan(r["unrealized_pnl"]))
    )
    cost_basis = holdings - total_pnl
    stocks  = pd.DataFrame(stock_rows)
    crypto  = pd.DataFrame(crypto_rows)
    options = pd.DataFrame(option_rows)
    return {
        "connected": True,
        "account": {
            "portfolio_value":      equity,
            "equity":               equity,
            "cash":                 cash,
            "buying_power":         buying_power,
            "holdings_value":       holdings,
            "total_unrealized_pnl": total_pnl,
            "total_cost_basis":     cost_basis,
            "total_pnl_pct":        (total_pnl / cost_basis * 100) if cost_basis else 0.0,
        },
        "accounts":  [_account_summary(a) for a in accounts],
        "stocks":    stocks,
        "crypto":    crypto,
        "options":   options,
        "positions": pd.concat([stocks, crypto], ignore_index=True) if (stock_rows or crypto_rows) else pd.DataFrame(),
        "orders":    pd.DataFrame(ord_rows),
        "debug": {
            "accounts": [
                {"id": a["id"], "institution_name": a.get("institution_name"),
                 "name": a.get("name"), "meta": a.get("meta")}
                for a in accounts
            ],
            "raw_options": raw_options,
            "raw_return_rates": raw_returns,
            "raw_activities": raw_activities,
            "counts": {"stocks": len(stock_rows), "crypto": len(crypto_rows),
                       "options": len(option_rows), "orders": len(ord_rows),
                       "activities": sum(len(v) for v in raw_activities.values())},
        },
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
