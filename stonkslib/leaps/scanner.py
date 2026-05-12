import yaml
import logging
import warnings
import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

from stonkslib.alerts.signals import check_signals
from stonkslib.utils.load_td import load_td

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = PROJECT_ROOT / "stonkslib" / "strategies"
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"

logger = logging.getLogger(__name__)


def get_vix_rank() -> tuple[float | None, float | None]:
    """Return (current_vix, vix_rank_percentile) from the past 52 weeks."""
    try:
        df = yf.download("^VIX", period="1y", interval="1d", progress=False)
        if df.empty:
            return None, None
        close = df["Close"].dropna().squeeze()
        current = float(close.iloc[-1])
        vix_min = float(close.min())
        vix_max = float(close.max())
        rank = (current - vix_min) / (vix_max - vix_min) * 100 if vix_max != vix_min else 50.0
        return round(current, 2), round(rank, 1)
    except Exception as e:
        logger.warning(f"[!] VIX fetch failed: {e}")
        return None, None


def _resolve_strategy_path(path: Path, ticker: str | None = None, option_type: str = "auto") -> Path:
    """Prefer LEAP-specific → ticker-specific → global optimized → base."""
    opt_dir = STRATEGY_DIR / "optimized"
    if ticker:
        leap_opt = opt_dir / f"{path.stem}_{ticker}_leaps_{option_type}_optimized.yaml"
        if leap_opt.exists():
            return leap_opt
        ticker_opt = opt_dir / f"{path.stem}_{ticker}_optimized.yaml"
        if ticker_opt.exists():
            return ticker_opt
    global_leap = opt_dir / f"{path.stem}_leaps_{option_type}_optimized.yaml"
    if global_leap.exists():
        return global_leap
    global_opt = opt_dir / f"{path.stem}_optimized.yaml"
    if global_opt.exists():
        return global_opt
    return path


def _ticker_category(ticker: str) -> str:
    try:
        with open(TICKER_YAML) as f:
            data = yaml.safe_load(f) or {}
        for cat, tickers in data.items():
            if tickers and ticker in tickers:
                return cat
    except Exception:
        pass
    return "stocks"


def _best_leap_option(ticker: str, current_price: float, direction: str) -> dict | None:
    """Return the best LEAP strike from the options chain (12–18 months out)."""
    try:
        t = yf.Ticker(ticker)
        expirations = t.options
        if not expirations:
            return None

        now = datetime.now()
        min_date = now + timedelta(days=365)
        max_date = now + timedelta(days=548)  # ~18 months

        valid = [e for e in expirations
                 if min_date <= datetime.strptime(e, "%Y-%m-%d") <= max_date]

        if not valid:
            beyond = [e for e in expirations if datetime.strptime(e, "%Y-%m-%d") >= min_date]
            if not beyond:
                return None
            valid = [beyond[0]]

        target_date = now + timedelta(days=456)  # ~15 months — sweet spot
        best_expiry = min(valid, key=lambda e: abs((datetime.strptime(e, "%Y-%m-%d") - target_date).days))

        chain = t.option_chain(best_expiry)
        df = chain.calls if direction == "CALL" else chain.puts

        # For calls: slightly ITM (~0.95x) for higher delta. For puts: ATM (~1.0x) for hedge.
        target_strike = current_price * (0.95 if direction == "CALL" else 1.0)

        liquid = df[df["openInterest"] > 50].copy()
        if liquid.empty:
            liquid = df.copy()

        liquid["_diff"] = (liquid["strike"] - target_strike).abs()
        best = liquid.loc[liquid["_diff"].idxmin()]

        return {
            "expiry": best_expiry,
            "strike": float(best["strike"]),
            "bid": round(float(best["bid"]), 2) if not pd.isna(best["bid"]) else None,
            "ask": round(float(best["ask"]), 2) if not pd.isna(best["ask"]) else None,
            "iv": round(float(best["impliedVolatility"]) * 100, 1) if not pd.isna(best["impliedVolatility"]) else None,
            "open_interest": int(best["openInterest"]) if not pd.isna(best["openInterest"]) else None,
        }
    except Exception as e:
        logger.debug(f"[!] Options chain failed for {ticker}: {e}")
        return None


def scan_leaps(tickers: list[str], interval: str = "1wk") -> tuple[list[dict], float | None, float | None]:
    """
    Scan tickers for LEAP call/put opportunities.

    Aggregates BUY/SELL signals across all strategies on the given interval,
    uses VIX rank as a market-wide IV proxy, and fetches the best LEAP strike
    from the options chain for non-crypto tickers.

    Returns (results, vix_current, vix_rank).
    """
    vix_current, vix_rank = get_vix_rank()
    logger.info(f"VIX: {vix_current} | Rank: {vix_rank}%")

    strategy_paths = list(STRATEGY_DIR.glob("*.yaml"))

    results = []

    for ticker in tickers:
        category = _ticker_category(ticker)

        data = load_td([ticker], interval)
        df = data.get(ticker)
        if df is None or df.empty:
            logger.warning(f"[!] No data for {ticker} — skipping")
            continue

        current_price = float(df["Close"].iloc[-1])

        buy_count = 0
        sell_count = 0
        buy_reasons: list[str] = []
        sell_reasons: list[str] = []

        for p in strategy_paths:
            resolved = _resolve_strategy_path(p, ticker)
            try:
                with open(resolved) as f:
                    strat = yaml.safe_load(f)
            except Exception:
                continue
            sigs = check_signals(ticker, interval, strat)
            if not sigs:
                continue
            for s in sigs:
                if s["type"] == "BUY":
                    buy_count += 1
                    buy_reasons.append(s["reason"])
                elif s["type"] == "SELL":
                    sell_count += 1
                    sell_reasons.append(s["reason"])

        if buy_count == 0 and sell_count == 0:
            continue

        direction = "CALL" if buy_count >= sell_count else "PUT"
        signal_count = max(buy_count, sell_count)
        top_reasons = buy_reasons[:3] if direction == "CALL" else sell_reasons[:3]

        option = None
        if category != "crypto":
            option = _best_leap_option(ticker, current_price, direction)

        results.append({
            "ticker": ticker,
            "category": category,
            "current_price": current_price,
            "direction": direction,
            "signal_count": signal_count,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "top_reasons": top_reasons,
            "vix": vix_current,
            "vix_rank": vix_rank,
            "option": option,
        })

    results.sort(key=lambda x: x["signal_count"], reverse=True)
    return results, vix_current, vix_rank
