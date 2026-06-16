"""Expression engine for v2 (self-contained) strategy YAMLs.

A v2 strategy carries its own buy/sell logic as `entry:` / `exit:` expression strings
evaluated against a namespace of named pandas Series built from the indicator
registry. This is the single shared implementation used by both the backtest
(`backtest/strategy.py`) and the alert scanner (`alerts/signals.py`), replacing the
hardcoded per-indicator logic that was previously duplicated across both.

Evaluation is **vectorized** (operates on whole Series) and **safe**: expressions are
parsed with the `ast` module and walked under a strict node/function whitelist — no
`eval()` of arbitrary code, no attribute access, no imports.
"""

import ast
import functools

import pandas as pd

from stonkslib.indicators.registry import INDICATORS, PRICE_OUTPUTS


# ── v2 detection ──────────────────────────────────────────────────────────────
def is_v2(strategy: dict) -> bool:
    """A strategy is v2 if it declares version 2 or carries entry/exit logic."""
    return bool(
        strategy.get("version") == 2
        or strategy.get("entry")
        or strategy.get("exit")
    )


# ── helper functions available inside expressions ─────────────────────────────
def _prev(x):
    return x.shift(1) if isinstance(x, pd.Series) else x


def _crossover(a, b):
    """a crosses above b: was <= on the previous bar, now strictly greater."""
    return (_prev(a) <= _prev(b)) & (a > b)


def _crossunder(a, b):
    """a crosses below b: was >= on the previous bar, now strictly less."""
    return (_prev(a) >= _prev(b)) & (a < b)


def _rising(x, n=1):
    return x > x.shift(int(n))


def _falling(x, n=1):
    return x < x.shift(int(n))


_FUNCS = {
    "crossover": _crossover,
    "crossunder": _crossunder,
    "rising": _rising,
    "falling": _falling,
    "abs": abs,
    "min": min,
    "max": max,
}

# Comparison and binary operators allowed in expressions.
_CMP = {
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
}
_BIN = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
}


class ExprError(ValueError):
    """Raised when an expression references unknown names or uses disallowed syntax."""


def _and(parts):
    return functools.reduce(lambda a, b: a & b, parts)


def _or(parts):
    return functools.reduce(lambda a, b: a | b, parts)


def _eval_node(node, ns):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, ns)

    if isinstance(node, ast.BoolOp):
        vals = [_eval_node(v, ns) for v in node.values]
        if isinstance(node.op, ast.And):
            return _and(vals)
        if isinstance(node.op, ast.Or):
            return _or(vals)
        raise ExprError(f"Unsupported boolean op: {type(node.op).__name__}")

    if isinstance(node, ast.UnaryOp):
        val = _eval_node(node.operand, ns)
        if isinstance(node.op, ast.Not):
            return ~val if isinstance(val, pd.Series) else (not val)
        if isinstance(node.op, ast.USub):
            return -val
        if isinstance(node.op, ast.UAdd):
            return +val
        raise ExprError(f"Unsupported unary op: {type(node.op).__name__}")

    if isinstance(node, ast.BinOp):
        op = _BIN.get(type(node.op))
        if op is None:
            raise ExprError(f"Unsupported binary op: {type(node.op).__name__}")
        return op(_eval_node(node.left, ns), _eval_node(node.right, ns))

    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, ns)
        result = None
        for op, comp in zip(node.ops, node.comparators):
            fn = _CMP.get(type(op))
            if fn is None:
                raise ExprError(f"Unsupported comparison: {type(op).__name__}")
            right = _eval_node(comp, ns)
            piece = fn(left, right)
            result = piece if result is None else (result & piece)
            left = right  # support chained comparisons (a < b < c)
        return result

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
            raise ExprError("Only whitelisted functions may be called")
        if node.keywords:
            raise ExprError("Keyword arguments are not allowed in expressions")
        args = [_eval_node(a, ns) for a in node.args]
        return _FUNCS[node.func.id](*args)

    if isinstance(node, ast.Name):
        if node.id not in ns:
            raise ExprError(f"Unknown name in expression: '{node.id}'")
        return ns[node.id]

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, bool)):
            return node.value
        raise ExprError(f"Unsupported constant: {node.value!r}")

    raise ExprError(f"Disallowed expression syntax: {type(node).__name__}")


def eval_expr(expr: str, ns: dict) -> pd.Series:
    """Evaluate an expression string against a namespace of named Series.

    Returns a boolean pandas Series (or a scalar bool for constant expressions).
    Raises ExprError on unknown names or disallowed syntax.
    """
    if not expr or not str(expr).strip():
        raise ExprError("Empty expression")
    try:
        tree = ast.parse(str(expr), mode="eval")
    except SyntaxError as e:
        raise ExprError(f"Could not parse expression: {e}") from e
    return _eval_node(tree, ns)


# ── namespace construction ────────────────────────────────────────────────────
def build_namespace(df: pd.DataFrame, strategy: dict) -> dict:
    """Compute only the indicators present in `indicators:` and return a flat
    namespace of named pandas Series the expressions can reference (plus OHLCV)."""
    ns = {}
    for name, col in PRICE_OUTPUTS.items():
        if col in df.columns:
            ns[name] = pd.to_numeric(df[col], errors="coerce")

    ind = strategy.get("indicators", {}) or {}
    for key, cfg in ind.items():
        spec = INDICATORS.get(key)
        if spec is None:
            raise ExprError(f"Unknown indicator '{key}' (not in registry)")
        # In v2, presence enables the indicator; tolerate a legacy `enabled: false`.
        if isinstance(cfg, dict) and cfg.get("enabled") is False:
            continue
        params = (cfg or {}).get("params", {}) if isinstance(cfg, dict) else {}
        kwargs = {fn_kw: params.get(yaml_key, default)
                  for yaml_key, (fn_kw, default) in spec["params"].items()}
        out = spec["fn"](df.copy(), **kwargs)
        for exposed, col in spec["outputs"].items():
            series = out if col is None else out[col]
            ns[exposed] = series
    return ns


def _coerce_bool_series(val, index) -> pd.Series:
    """Normalize an expression result into a boolean Series aligned to `index`,
    treating NaN comparisons as False (no signal)."""
    if isinstance(val, pd.Series):
        return val.reindex(index).fillna(False).astype(bool)
    return pd.Series(bool(val), index=index)


def entry_signals(df, strategy, ns=None) -> pd.Series:
    ns = ns if ns is not None else build_namespace(df, strategy)
    expr = strategy.get("entry")
    if not expr:
        return pd.Series(False, index=df.index)
    return _coerce_bool_series(eval_expr(expr, ns), df.index)


def exit_signals(df, strategy, ns=None) -> pd.Series:
    ns = ns if ns is not None else build_namespace(df, strategy)
    expr = strategy.get("exit")
    if not expr:
        return pd.Series(False, index=df.index)
    return _coerce_bool_series(eval_expr(expr, ns), df.index)


def vote_signals(df, strategy, ns=None) -> dict:
    """Per-indicator BUY/SELL confluence votes as boolean Series, keyed by source.

    Uses each strategy indicator's `vote_buy`/`vote_sell` override if present, else
    the registry default. Returns {"BUY": {src: Series}, "SELL": {src: Series}}.
    """
    ns = ns if ns is not None else build_namespace(df, strategy)
    ind = strategy.get("indicators", {}) or {}
    out = {"BUY": {}, "SELL": {}}
    for key, cfg in ind.items():
        spec = INDICATORS.get(key)
        if spec is None:
            continue
        if isinstance(cfg, dict) and cfg.get("enabled") is False:
            continue
        cfg = cfg or {}
        buy_expr = cfg.get("vote_buy", spec["vote_buy"]) if isinstance(cfg, dict) else spec["vote_buy"]
        sell_expr = cfg.get("vote_sell", spec["vote_sell"]) if isinstance(cfg, dict) else spec["vote_sell"]
        if buy_expr:
            out["BUY"][key] = _coerce_bool_series(eval_expr(buy_expr, ns), df.index)
        if sell_expr:
            out["SELL"][key] = _coerce_bool_series(eval_expr(sell_expr, ns), df.index)
    return out


def confluence_scores(df, strategy, ns=None):
    """Weighted per-bar BUY / SELL confluence score Series.

    Each indicator that votes in a direction contributes its weight (from
    `confluence.weights`, default 1.0). Returns (buy_score, sell_score) Series.
    Mirrors the alert-path `confluence_score()` semantics but vectorized over all bars,
    so the backtest can gate entries on it.
    """
    ns = ns if ns is not None else build_namespace(df, strategy)
    votes = vote_signals(df, strategy, ns)
    weights = (strategy.get("confluence") or {}).get("weights", {}) or {}
    buy = pd.Series(0.0, index=df.index)
    sell = pd.Series(0.0, index=df.index)
    for src, series in votes["BUY"].items():
        buy += series.astype(float) * float(weights.get(src, 1.0))
    for src, series in votes["SELL"].items():
        sell += series.astype(float) * float(weights.get(src, 1.0))
    return buy, sell


def validate_strategy(strategy: dict) -> list[str]:
    """Return a list of human-readable problems with a v2 strategy spec (empty = ok).

    Used by the Add-Strategy page and tests to validate a pasted/edited spec before save.
    """
    problems = []
    ind = strategy.get("indicators", {}) or {}
    for key in ind:
        if key not in INDICATORS:
            problems.append(f"Unknown indicator '{key}'")

    # Build an empty namespace of all *declared* names so expr names can be checked
    # without computing anything.
    declared = set(PRICE_OUTPUTS)
    for key in ind:
        spec = INDICATORS.get(key)
        if spec:
            declared.update(spec["outputs"])
    probe = {n: pd.Series(dtype=float) for n in declared}

    for field in ("entry", "exit"):
        expr = strategy.get(field)
        if not expr:
            continue
        try:
            eval_expr(expr, probe)
        except ExprError as e:
            problems.append(f"{field}: {e}")
    return problems
