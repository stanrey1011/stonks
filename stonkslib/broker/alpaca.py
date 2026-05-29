"""
Alpaca Markets broker integration.

Set in .env:
    ALPACA_API_KEY=...          # paper account key
    ALPACA_SECRET_KEY=...       # paper account secret
    ALPACA_PAPER=true

    ALPACA_LIVE_API_KEY=...     # live account key (optional)
    ALPACA_LIVE_SECRET_KEY=...  # live account secret (optional)
"""
import os
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_PAPER_KEY    = os.getenv("ALPACA_API_KEY", "")
_PAPER_SECRET = os.getenv("ALPACA_SECRET_KEY", "")
_LIVE_KEY     = os.getenv("ALPACA_LIVE_API_KEY", "")
_LIVE_SECRET  = os.getenv("ALPACA_LIVE_SECRET_KEY", "")

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit


def _trading_client(live: bool = False) -> TradingClient:
    if live:
        return TradingClient(_LIVE_KEY, _LIVE_SECRET, paper=False)
    return TradingClient(_PAPER_KEY, _PAPER_SECRET, paper=True)


def _data_client() -> StockHistoricalDataClient:
    return StockHistoricalDataClient(_PAPER_KEY, _PAPER_SECRET)


def is_live_configured() -> bool:
    return bool(_LIVE_KEY and _LIVE_SECRET)


# ── account ───────────────────────────────────────────────────────────────────

def get_account(live: bool = False) -> dict:
    """Return key account fields. live=True uses the live account keys."""
    acct = _trading_client(live).get_account()
    return {
        "equity":          float(acct.equity),
        "cash":            float(acct.cash),
        "buying_power":    float(acct.buying_power),
        "portfolio_value": float(acct.portfolio_value),
        "live":            live,
    }


def get_positions(live: bool = False) -> pd.DataFrame:
    """Return all open positions as a DataFrame."""
    positions = _trading_client(live).get_all_positions()
    if not positions:
        return pd.DataFrame()
    rows = [{
        "symbol":            p.symbol,
        "qty":               float(p.qty),
        "avg_cost":          float(p.avg_entry_price),
        "market_value":      float(p.market_value),
        "unrealized_pnl":    float(p.unrealized_pl),
        "unrealized_pnl_pct": float(p.unrealized_plpc) * 100,
    } for p in positions]
    return pd.DataFrame(rows)


def get_orders(live: bool = False, limit: int = 20) -> pd.DataFrame:
    """Return recent orders as a DataFrame."""
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus
    req = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=limit)
    orders = _trading_client(live).get_orders(filter=req)
    if not orders:
        return pd.DataFrame()
    rows = [{
        "symbol":     o.symbol,
        "side":       str(o.side).replace("OrderSide.", ""),
        "qty":        float(o.qty) if o.qty else None,
        "filled_qty": float(o.filled_qty) if o.filled_qty else 0,
        "type":       str(o.type).replace("OrderType.", ""),
        "status":     str(o.status).replace("OrderStatus.", ""),
        "submitted":  str(o.submitted_at)[:16] if o.submitted_at else "",
        "filled_avg": float(o.filled_avg_price) if o.filled_avg_price else None,
    } for o in orders]
    return pd.DataFrame(rows)


# ── market data ───────────────────────────────────────────────────────────────

def _interval_to_timeframe(interval: str) -> TimeFrame:
    mapping = {
        "1d":  TimeFrame(1,  TimeFrameUnit.Day),
        "1wk": TimeFrame(1,  TimeFrameUnit.Week),
        "1h":  TimeFrame(1,  TimeFrameUnit.Hour),
        "30m": TimeFrame(30, TimeFrameUnit.Minute),
        "15m": TimeFrame(15, TimeFrameUnit.Minute),
        "5m":  TimeFrame(5,  TimeFrameUnit.Minute),
        "1m":  TimeFrame(1,  TimeFrameUnit.Minute),
    }
    if interval not in mapping:
        raise ValueError(f"Unsupported interval '{interval}'. Use: {list(mapping)}")
    return mapping[interval]


def get_bars(
    ticker: str,
    interval: str = "1d",
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 1000,
) -> pd.DataFrame:
    """Fetch OHLCV bars from Alpaca (IEX feed, free-tier compatible)."""
    if end is None:
        end = datetime.now(timezone.utc)
    if start is None:
        from datetime import timedelta
        days = {"1d": 3650, "1wk": 3650, "1h": 730, "30m": 60, "15m": 60, "5m": 60, "1m": 7}
        start = end - timedelta(days=days.get(interval, 365))

    req = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=_interval_to_timeframe(interval),
        start=start,
        end=end,
        limit=limit,
        adjustment="all",
        feed="iex",
    )
    bars = _data_client().get_stock_bars(req).df

    if bars.empty:
        return pd.DataFrame()

    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs(ticker, level="symbol")

    bars.index.name = "Date"
    bars = bars.rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume",
    })[["Open", "High", "Low", "Close", "Volume"]]

    return bars.sort_index()


# ── portfolio history ─────────────────────────────────────────────────────────

def get_portfolio_history(
    live: bool = False,
    period: str = "1M",
    timeframe: str = "1D",
) -> pd.DataFrame:
    """
    Return equity curve as a DataFrame: timestamp index, columns equity / pnl / pnl_pct.
    period:    1D 1W 1M 3M 6M 1A all
    timeframe: 1Min 5Min 15Min 1H 1D
    """
    from alpaca.trading.requests import GetPortfolioHistoryRequest
    req = GetPortfolioHistoryRequest(period=period, timeframe=timeframe)
    h = _trading_client(live).get_portfolio_history(history_filter=req)
    if not h or not h.timestamp:
        return pd.DataFrame()
    rows = []
    for i, ts in enumerate(h.timestamp):
        eq  = h.equity[i]          if h.equity          else None
        pl  = h.profit_loss[i]     if h.profit_loss      else None
        plp = h.profit_loss_pct[i] if h.profit_loss_pct  else None
        if eq is not None:
            rows.append({
                "timestamp": pd.Timestamp(ts, unit="s", tz="UTC"),
                "equity":    float(eq),
                "pnl":       float(pl)  if pl  is not None else 0.0,
                "pnl_pct":   float(plp) * 100 if plp is not None else 0.0,
            })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("timestamp").sort_index()


# ── watchlist sync ────────────────────────────────────────────────────────────

_WATCHLIST_NAME = "Stonks"


def get_watchlist(live: bool = False) -> list[str]:
    """Return symbols in the Stonks Alpaca watchlist, or [] if it doesn't exist."""
    client = _trading_client(live)
    try:
        for wl in client.get_watchlists():
            if wl.name == _WATCHLIST_NAME:
                detail = client.get_watchlist_by_id(wl.id)
                return [a.symbol for a in (detail.assets or [])]
    except Exception:
        pass
    return []


def sync_watchlist(tickers: list[str], live: bool = False) -> dict:
    """
    Push tickers to the Alpaca 'Stonks' watchlist (creates if missing).
    Skips crypto — Alpaca watchlists only support equity symbols.
    Returns {"created": bool, "symbols": list[str]}.
    """
    from alpaca.trading.requests import CreateWatchlistRequest, UpdateWatchlistRequest

    symbols = [t for t in tickers if not t.upper().endswith(("-USD", "-USDT"))]
    client  = _trading_client(live)
    wls     = client.get_watchlists()
    existing = next((wl for wl in wls if wl.name == _WATCHLIST_NAME), None)

    if existing:
        client.update_watchlist_by_id(
            existing.id,
            UpdateWatchlistRequest(name=_WATCHLIST_NAME, symbols=symbols),
        )
        return {"created": False, "symbols": symbols}

    client.create_watchlist(CreateWatchlistRequest(name=_WATCHLIST_NAME, symbols=symbols))
    return {"created": True, "symbols": symbols}


# ── orders ────────────────────────────────────────────────────────────────────

def place_market_order(
    ticker: str,
    qty: float,
    side: str = "buy",
    time_in_force: str = "day",
    live: bool = False,
) -> dict:
    """Place a market order. side='buy' or 'sell'."""
    req = MarketOrderRequest(
        symbol=ticker,
        qty=qty,
        side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY if time_in_force == "day" else TimeInForce.GTC,
    )
    order = _trading_client(live).submit_order(req)
    return {"id": str(order.id), "status": str(order.status),
            "symbol": order.symbol, "qty": float(order.qty)}


def place_limit_order(
    ticker: str,
    qty: float,
    limit_price: float,
    side: str = "buy",
    time_in_force: str = "gtc",
    live: bool = False,
) -> dict:
    """Place a limit order."""
    req = LimitOrderRequest(
        symbol=ticker,
        qty=qty,
        limit_price=limit_price,
        side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
        time_in_force=TimeInForce.GTC if time_in_force == "gtc" else TimeInForce.DAY,
    )
    order = _trading_client(live).submit_order(req)
    return {"id": str(order.id), "status": str(order.status),
            "symbol": order.symbol, "qty": float(order.qty),
            "limit_price": float(order.limit_price)}


def cancel_all_orders(live: bool = False) -> int:
    """Cancel all open orders. Returns count cancelled."""
    cancelled = _trading_client(live).cancel_orders()
    return len(cancelled)
