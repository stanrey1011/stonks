# stonkslib/indicators/extrema.py
"""
Local-extrema (swing high/low) detection and "timing quality" scoring.

Timing quality answers the question the user asks by eye on the Confluence chart:
"did this BUY land near a local low, and this SELL near a local high?" — turned
into a number so strategy/confluence changes can be compared objectively.

Reuses the same swing-point primitive (`scipy.signal.argrelextrema`) already used
by the pattern detectors (see stonkslib/patterns/wedges.py).
"""

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema

# A mean entry/exit this far (fraction) from the nearest swing point scores 0.
# Most entries land 2-12% off the local low/high, so 15% gives that band useful
# resolution (3% -> 80, 7% -> 53) while flooring genuinely bad timing. Tunable.
TIMING_ERROR_CAP = 0.15


def find_local_extrema(df, col="Close", window=5):
    """
    Return positional indices of local swing highs and lows of `df[col]`.

    A point is a swing high if it is >= its neighbours within +/- `window` bars
    (symmetric for lows). Returns (highs_idx, lows_idx) as numpy int arrays of
    positional indices into `df`.
    """
    prices = pd.to_numeric(df[col], errors="coerce").to_numpy()
    if len(prices) == 0:
        return np.array([], dtype=int), np.array([], dtype=int)
    highs_idx = argrelextrema(prices, np.greater_equal, order=window)[0]
    lows_idx = argrelextrema(prices, np.less_equal, order=window)[0]
    return highs_idx, lows_idx


def _nearest_extreme_error(prices, pos, extrema_idx, fill_price, kind):
    """
    Distance from a fill to the nearest swing extreme, as a fraction.

    kind="low":  err = (fill - nearest_low) / nearest_low   (bought above the low)
    kind="high": err = (nearest_high - fill) / nearest_high  (sold below the high)

    Clipped at 0 — filling at or beyond the swing point (a better price than the
    detected extreme) counts as perfect timing, not negative error.
    """
    if len(extrema_idx) == 0 or fill_price is None or fill_price <= 0:
        return None
    nearest = int(extrema_idx[np.argmin(np.abs(extrema_idx - pos))])
    extreme_price = float(prices[nearest])
    if extreme_price <= 0:
        return None
    if kind == "low":
        err = (float(fill_price) - extreme_price) / extreme_price
    else:  # high
        err = (extreme_price - float(fill_price)) / extreme_price
    return max(0.0, err)


def timing_quality(df, trades, col="Close", window=5):
    """
    Score how close each backtest fill sat to a local swing point.

    `trades` is the list produced by run_strategy_backtest(): dicts with
    `action` ("BUY"/"SELL"/"SELL_END"), `date` (str(index)) and `price`.

    Returns a metrics dict:
      timing_score      0-100, higher = better-timed entries/exits (None if no trades scored)
      timing_mean_err   mean fractional distance from the nearest swing point
      timing_median_err median fractional distance
      timing_buy_err    mean error for BUYs (distance above the local low)
      timing_sell_err   mean error for SELLs (distance below the local high)
      timing_n          number of fills scored
    """
    empty = {
        "timing_score": None, "timing_mean_err": None, "timing_median_err": None,
        "timing_buy_err": None, "timing_sell_err": None, "timing_n": 0,
    }
    if df is None or len(df) == 0 or not trades:
        return empty

    prices = pd.to_numeric(df[col], errors="coerce").to_numpy()
    highs_idx, lows_idx = find_local_extrema(df, col=col, window=window)
    date_to_pos = {str(ts): p for p, ts in enumerate(df.index)}

    buy_errs, sell_errs = [], []
    for t in trades:
        pos = date_to_pos.get(t.get("date"))
        if pos is None:
            continue
        action = t.get("action")
        price = t.get("price")
        if action == "BUY":
            err = _nearest_extreme_error(prices, pos, lows_idx, price, "low")
            if err is not None:
                buy_errs.append(err)
        elif action in ("SELL", "SELL_END"):
            err = _nearest_extreme_error(prices, pos, highs_idx, price, "high")
            if err is not None:
                sell_errs.append(err)

    all_errs = buy_errs + sell_errs
    if not all_errs:
        return empty

    mean_err = float(np.mean(all_errs))
    score = round(100.0 * (1.0 - min(mean_err / TIMING_ERROR_CAP, 1.0)), 1)
    return {
        "timing_score": score,
        "timing_mean_err": round(mean_err, 4),
        "timing_median_err": round(float(np.median(all_errs)), 4),
        "timing_buy_err": round(float(np.mean(buy_errs)), 4) if buy_errs else None,
        "timing_sell_err": round(float(np.mean(sell_errs)), 4) if sell_errs else None,
        "timing_n": len(all_errs),
    }
