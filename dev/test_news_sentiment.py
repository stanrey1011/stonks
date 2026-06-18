"""Tests for the news_sentiment indicator's bar-alignment logic.

These exercise alignment/ffill/shift purely against in-memory score rows — the
news store is monkeypatched, so no SQLite/Finnhub/LLM is touched.

Run standalone:   python dev/test_news_sentiment.py
Or with pytest:   pytest dev/test_news_sentiment.py
"""

import os
import sys

import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import stonkslib.indicators.news_sentiment as ns_mod
from stonkslib.indicators.news_sentiment import news_sentiment


def _patch_scores(rows):
    """Make news_store.load_score_rows return fixed (date, score) rows."""
    ns_mod.news_store.load_score_rows = lambda ticker: rows


def _df(idx, ticker="T"):
    df = pd.DataFrame({"Close": range(len(idx))}, index=idx)
    if ticker is not None:
        df.attrs["ticker"] = ticker
    return df


def _vals(s):
    """Series -> list with None for NaN, for easy comparison."""
    return [None if pd.isna(v) else float(v) for v in s]


def test_no_ticker_returns_all_nan():
    _patch_scores([("2026-06-02", 8.0)])
    idx = pd.date_range("2026-06-01", periods=4, freq="D")
    out = news_sentiment(_df(idx, ticker=None))
    assert out.name == "news_sent"
    assert _vals(out) == [None, None, None, None]


def test_no_scores_returns_all_nan():
    _patch_scores([])
    idx = pd.date_range("2026-06-01", periods=4, freq="D")
    out = news_sentiment(_df(idx))
    assert _vals(out) == [None, None, None, None]


def test_basic_alignment_and_shift():
    # scores on Jun 2 (=8) and Jun 4 (=3); default lookback=1, shift=1.
    _patch_scores([("2026-06-02", 8.0), ("2026-06-04", 3.0)])
    idx = pd.date_range("2026-06-01", periods=6, freq="D")  # Jun 1..6
    out = news_sentiment(_df(idx))
    # ffill(limit=1): Jun2=8,Jun3=8,Jun4=3,Jun5=3 ; then shift(1) by one bar.
    assert _vals(out) == [None, None, 8.0, 8.0, 3.0, 3.0]


def test_no_lookahead():
    # With shift=1 the bar ON the score date must NOT see its own same-day score.
    _patch_scores([("2026-06-02", 8.0)])
    idx = pd.date_range("2026-06-01", periods=4, freq="D")
    out = news_sentiment(_df(idx), lookback=1, shift=1)
    # Jun2 (index pos 1) is the score date -> still NaN after the shift; the score
    # only becomes visible from Jun3 onward. (No bar ever sees its own same-day news.)
    assert _vals(out) == [None, None, 8.0, 8.0]


def test_lookback_carry_forward():
    # shift=0 to inspect raw carry; score on Jun 2 carries up to lookback=3 days.
    _patch_scores([("2026-06-02", 8.0)])
    idx = pd.date_range("2026-06-01", periods=6, freq="D")  # Jun 1..6
    out = news_sentiment(_df(idx), lookback=3, shift=0)
    assert _vals(out) == [None, 8.0, 8.0, 8.0, 8.0, None]


def test_weekend_news_reaches_next_trading_day():
    # News dated Saturday Jun 6 should reach the Monday Jun 8 bar via calendar ffill.
    _patch_scores([("2026-06-06", 7.0)])
    idx = pd.to_datetime(["2026-06-05", "2026-06-08", "2026-06-09"])  # Fri, Mon, Tue
    out = news_sentiment(_df(idx), lookback=3, shift=0)
    assert _vals(out) == [None, 7.0, 7.0]


def test_tz_aware_index():
    # tz-aware bar index (as produced by some parquet loads) must not raise.
    _patch_scores([("2026-06-02", 5.0)])
    idx = pd.date_range("2026-06-01", periods=4, freq="D", tz="UTC")
    out = news_sentiment(_df(idx), lookback=1, shift=0)
    assert _vals(out) == [None, 5.0, 5.0, None]
    assert out.index.equals(idx)  # output stays aligned to the original index


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
