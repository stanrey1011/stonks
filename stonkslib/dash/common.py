from pathlib import Path
import json
import shutil
import yaml
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
TICKER_EXAMPLE = PROJECT_ROOT / "tickers.example.yaml"
STRATEGY_DIR = PROJECT_ROOT / "stonkslib" / "strategies"
BACKTEST_DIR = PROJECT_ROOT / "data" / "backtest_results" / "strategy"
CLEAN_DIR = PROJECT_ROOT / "data" / "ticker_data" / "clean"
SIGNALS_DIR  = PROJECT_ROOT / "data" / "analysis" / "signals"
MERGED_DIR   = PROJECT_ROOT / "data" / "analysis" / "merged" / "by-indicators"
_stonks_which = shutil.which("stonks")
STONKS_BIN = Path(_stonks_which) if _stonks_which else PROJECT_ROOT / "venv" / "bin" / "stonks"

INTERVALS = ["1d", "1wk", "1h", "1m", "2m", "5m", "15m", "30m"]
VALID_CATEGORIES = ["stocks", "crypto", "etfs"]
ALERT_CACHE_FILE = PROJECT_ROOT / "data" / "last_alert.json"


def load_watchlist() -> dict:
    # Seed a per-host watchlist from the committed example on first run (tickers.yaml
    # is gitignored, so a fresh checkout/container won't have one yet).
    if not TICKER_YAML.exists() and TICKER_EXAMPLE.exists():
        shutil.copy(TICKER_EXAMPLE, TICKER_YAML)
    with open(TICKER_YAML) as f:
        return yaml.safe_load(f) or {}


def save_watchlist(data: dict):
    with open(TICKER_YAML, "w") as f:
        yaml.dump(data, f, default_flow_style=False)


def flat_tickers(data: dict = None) -> list[str]:
    data = data or load_watchlist()
    return [t for items in data.values() for t in (items or [])]


def save_alert_cache(results: dict, ts: str, interval: str, min_signals: int):
    ALERT_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ts": ts, "interval": interval, "min_signals": min_signals, "results": results}
    with open(ALERT_CACHE_FILE, "w") as f:
        json.dump(payload, f)


def load_alert_cache() -> dict:
    """Returns dict with keys: results, ts, interval, min_signals. Empty dict if no cache."""
    if not ALERT_CACHE_FILE.exists():
        return {}
    try:
        with open(ALERT_CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


@st.cache_resource(show_spinner=False)
def load_ticker_data(ticker: str, interval: str) -> pd.DataFrame | None:
    path = CLEAN_DIR / ticker / f"{interval}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df.columns = df.columns.str.title()
    return df.sort_index()


# ── shared broker renderers ─────────────────────────────────────────────────────
# Every broker module (alpaca, robinhood, ibkr) returns the same canonical schema,
# so these render helpers are reused across the per-broker dashboard pages.

def render_account_metrics(acct: dict):
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Portfolio Value", f"${acct.get('portfolio_value', 0):,.2f}")
    m2.metric("Equity",          f"${acct.get('equity', 0):,.2f}")
    m3.metric("Cash",            f"${acct.get('cash', 0):,.2f}")
    m4.metric("Buying Power",    f"${acct.get('buying_power', 0):,.2f}")


def render_positions_table(df: pd.DataFrame):
    if df is None or df.empty:
        st.info("No open positions.")
        return
    col_cfg = {
        "symbol":             st.column_config.TextColumn("Symbol",    width="small"),
        "qty":                st.column_config.NumberColumn("Qty",     format="%.4g", width="small"),
        "avg_cost":           st.column_config.NumberColumn("Avg Cost", format="$%.2f", width="small"),
        "market_value":       st.column_config.NumberColumn("Mkt Value", format="$%.2f", width="small"),
        "unrealized_pnl":     st.column_config.NumberColumn("Unreal P&L", format="$%.2f", width="small"),
        "unrealized_pnl_pct": st.column_config.NumberColumn("P&L %", format="%.2f%%", width="small"),
    }
    st.dataframe(df, column_config=col_cfg, use_container_width=True, hide_index=True)


def render_options_table(df: pd.DataFrame):
    if df is None or df.empty:
        st.info("No open option positions.")
        return
    col_cfg = {
        "symbol":             st.column_config.TextColumn("Underlying", width="small"),
        "contract":           st.column_config.TextColumn("Contract",   width="medium"),
        "type":               st.column_config.TextColumn("Type",       width="small"),
        "strike":             st.column_config.NumberColumn("Strike",   format="$%.2f", width="small"),
        "expiry":             st.column_config.TextColumn("Expiry",     width="small"),
        "qty":                st.column_config.NumberColumn("Contracts", format="%.4g", width="small"),
        "avg_cost":           st.column_config.NumberColumn("Avg Cost", format="$%.2f", width="small"),
        "market_value":       st.column_config.NumberColumn("Mkt Value", format="$%.2f", width="small"),
        "unrealized_pnl":     st.column_config.NumberColumn("Unreal P&L", format="$%.2f", width="small"),
        "unrealized_pnl_pct": st.column_config.NumberColumn("P&L %", format="%.2f%%", width="small"),
    }
    st.dataframe(df, column_config=col_cfg, use_container_width=True, hide_index=True)


def render_orders_table(df: pd.DataFrame):
    if df is None or df.empty:
        st.info("No recent orders.")
        return
    col_cfg = {
        "symbol":     st.column_config.TextColumn("Symbol",     width="small"),
        "side":       st.column_config.TextColumn("Side",       width="small"),
        "qty":        st.column_config.NumberColumn("Qty",      format="%.4g", width="small"),
        "filled_qty": st.column_config.NumberColumn("Filled",   format="%.4g", width="small"),
        "type":       st.column_config.TextColumn("Type",       width="small"),
        "status":     st.column_config.TextColumn("Status",     width="small"),
        "submitted":  st.column_config.TextColumn("Submitted",  width="medium"),
        "filled_avg": st.column_config.NumberColumn("Fill Price", format="$%.2f", width="small"),
    }
    st.dataframe(df, column_config=col_cfg, use_container_width=True, hide_index=True)
