"""News-sentiment indicator.

Exposes the precomputed daily LLM sentiment score (1-10) as a bar-aligned Series
named `news_sent`, for use in strategy expressions and as a confluence vote.

It does NOT call an LLM — it only reads scores already written to the news store by
`sentiment.scorer`. That keeps backtests deterministic and fast (the LLM is a batch
data producer, never in the live signal path).

The ticker is read from `df.attrs["ticker"]` (set in `utils/load_td.load_td`), since
the engine's `build_namespace` passes only the price frame to indicator functions and
`.copy()` preserves `.attrs`. If no ticker or no scores are available the indicator
returns all-NaN, which the engine treats as "no signal".
"""

import pandas as pd

from stonkslib.utils import news_store


def news_sentiment(df: pd.DataFrame, lookback: int = 1, shift: int = 1) -> pd.Series:
    """Return a Series of daily sentiment scores (1-10) aligned to `df.index`.

    lookback — calendar days a score carries forward (forward-fill limit).
    shift    — bars to delay the score so a bar never sees its own same-day news
               (default 1 = no look-ahead).
    """
    idx = df.index
    empty = pd.Series(float("nan"), index=idx, name="news_sent")

    ticker = df.attrs.get("ticker")
    if not ticker:
        return empty

    rows = news_store.load_score_rows(ticker)
    if not rows:
        return empty

    # date-string -> score (rows are ascending, so last write wins per date)
    daily = pd.Series({d: sc for d, sc in rows})
    daily.index = pd.to_datetime(daily.index)  # tz-naive calendar dates
    daily = daily.sort_index()

    # bar dates as tz-naive calendar dates (handles tz-aware parquet indexes)
    bar_dates = pd.to_datetime(pd.Index(pd.to_datetime(idx)).strftime("%Y-%m-%d"))

    # forward-fill on a continuous calendar so weekend/holiday news reaches the next bar
    start = min(daily.index.min(), bar_dates.min())
    end = max(daily.index.max(), bar_dates.max())
    calendar = daily.reindex(pd.date_range(start, end, freq="D")).ffill(limit=int(lookback))

    out = pd.Series(calendar.reindex(bar_dates).to_numpy(), index=idx, name="news_sent")
    if shift:
        out = out.shift(int(shift))
    return out
