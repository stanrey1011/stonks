"""Tests for the v2 strategy expression engine.

Run standalone:   python dev/test_engine.py
Or with pytest:   pytest dev/test_engine.py
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from stonkslib.strategies.engine import (
    eval_expr, build_namespace, entry_signals, exit_signals,
    vote_signals, validate_strategy, ExprError,
)


def _ns(idx):
    return {
        "rsi": pd.Series([40, 25, 28, 35, 80, 75, 20, 15, 60, 90.0], index=idx),
        "macd": pd.Series([-1, 0.5, 0.2, -0.3, 1, 2, -1, -2, 0.5, 1.0], index=idx),
        "close": pd.Series([100, 101, 99, 98, 102, 103, 97, 96, 105, 110.0], index=idx),
    }


def test_boolean_and_comparison():
    idx = pd.date_range("2024-01-01", periods=10, freq="D")
    ns = _ns(idx)
    out = eval_expr("rsi < 30 and macd > 0", ns)
    assert list(out.astype(int)) == [0, 1, 1, 0, 0, 0, 0, 0, 0, 0]


def test_chained_comparison():
    idx = pd.date_range("2024-01-01", periods=10, freq="D")
    out = eval_expr("20 < rsi < 70", _ns(idx))
    assert list(out.astype(int)) == [1, 1, 1, 1, 0, 0, 0, 0, 1, 0]


def test_crossover_and_crossunder():
    idx = pd.date_range("2024-01-01", periods=10, freq="D")
    ns = _ns(idx)
    co = eval_expr("crossover(close, 100)", ns)
    assert list(co.astype(int)) == [0, 1, 0, 0, 1, 0, 0, 0, 1, 0]
    cu = eval_expr("crossunder(macd, 0)", ns)
    # macd goes +->- at idx 3 (0.2 -> -0.3) and idx 6 (2 -> -1)
    assert list(cu.astype(int)) == [0, 0, 0, 1, 0, 0, 1, 0, 0, 0]


def test_not_operator():
    idx = pd.date_range("2024-01-01", periods=10, freq="D")
    out = eval_expr("not (rsi > 70)", _ns(idx))
    assert list(out.astype(int)) == [1, 1, 1, 1, 0, 0, 1, 1, 1, 0]


def test_rejects_disallowed_syntax():
    idx = pd.date_range("2024-01-01", periods=10, freq="D")
    ns = _ns(idx)
    for bad in ['__import__("os")', "close.values", "rsi.__class__",
                "open('x')", "(1, 2)", "[1, 2]", "lambda: 1"]:
        try:
            eval_expr(bad, ns)
        except ExprError:
            continue
        except Exception:
            # syntax that doesn't even parse as an expression is also "rejected"
            continue
        raise AssertionError(f"expression should have been rejected: {bad}")


def test_rejects_unknown_name():
    idx = pd.date_range("2024-01-01", periods=10, freq="D")
    try:
        eval_expr("rsi < foo", _ns(idx))
    except ExprError:
        return
    raise AssertionError("unknown name should raise ExprError")


def _synthetic_df(n=120, seed=3):
    np.random.seed(seed)
    t = np.arange(n)
    close = 100 + 10 * np.sin(t / 8.0) + np.cumsum(np.random.normal(0, 0.5, n))
    close = np.maximum(close, 5)
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99,
         "Close": close, "Volume": np.full(n, 1e6)},
        index=pd.date_range("2023-01-01", periods=n, freq="D"),
    )


def test_build_namespace_and_signals():
    df = _synthetic_df()
    strat = {
        "version": 2,
        "indicators": {"rsi": {"params": {"period": 7}}, "macd": {"params": {}}},
        "entry": "rsi < 30 and macd > 0",
        "exit": "rsi > 70",
    }
    ns = build_namespace(df, strat)
    assert {"open", "high", "low", "close", "volume", "rsi", "macd", "macd_signal"} <= set(ns)
    ent = entry_signals(df, strat, ns)
    ext = exit_signals(df, strat, ns)
    assert ent.dtype == bool and ext.dtype == bool
    assert len(ent) == len(df)
    votes = vote_signals(df, strat, ns)
    assert set(votes["BUY"]) == {"rsi", "macd"}


def test_validate_strategy():
    assert validate_strategy({
        "indicators": {"rsi": {}, "macd": {}},
        "entry": "rsi < 30 and macd > 0", "exit": "rsi > 70",
    }) == []
    assert validate_strategy({"indicators": {"nope": {}}, "entry": "rsi < 30"})
    assert validate_strategy({"indicators": {"rsi": {}}, "entry": "rsi < bar"})


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
