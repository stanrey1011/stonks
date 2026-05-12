from pathlib import Path
import yaml
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"
STRATEGY_DIR = PROJECT_ROOT / "stonkslib" / "strategies"
BACKTEST_DIR = PROJECT_ROOT / "data" / "backtest_results" / "strategy"
CLEAN_DIR = PROJECT_ROOT / "data" / "ticker_data" / "clean"
SIGNALS_DIR = PROJECT_ROOT / "data" / "analysis" / "signals"
STONKS_BIN = PROJECT_ROOT / "venv" / "bin" / "stonks"

INTERVALS = ["1d", "1wk", "1h", "1m", "2m", "5m", "15m", "30m"]
VALID_CATEGORIES = ["stocks", "crypto", "etfs"]


def load_watchlist() -> dict:
    with open(TICKER_YAML) as f:
        return yaml.safe_load(f) or {}


def save_watchlist(data: dict):
    with open(TICKER_YAML, "w") as f:
        yaml.dump(data, f, default_flow_style=False)


def flat_tickers(data: dict = None) -> list[str]:
    data = data or load_watchlist()
    return [t for items in data.values() for t in (items or [])]


def load_ticker_data(ticker: str, interval: str) -> pd.DataFrame | None:
    path = CLEAN_DIR / ticker / f"{interval}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df.columns = df.columns.str.title()
    return df.sort_index()
