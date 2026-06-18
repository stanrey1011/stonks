"""Indicator registry — the single place an indicator registers for the v2
expression-based strategy engine.

Each entry maps an indicator key (as used in a strategy YAML's `indicators:` block)
to everything the engine needs to compute it and expose its outputs as named series
that `entry:` / `exit:` / confluence-vote expressions can reference.

Schema of an entry:
    fn        callable(df, **kwargs) -> Series | DataFrame   (the existing indicator fn)
    needs     list[str]   OHLCV columns the fn requires (title-cased)
    params    dict[yaml_key -> (fn_kwarg, default)]
                  Maps a strategy YAML param key to the indicator function's kwarg.
                  Params not listed here (e.g. rsi `overbought`) are thresholds used
                  only inside expressions and are ignored at compute time.
    outputs   dict[exposed_name -> column | None]
                  Names the expressions can reference. `None` means the fn returns a
                  Series and that series *is* the value; a string selects that column
                  from the returned DataFrame.
    vote_buy  str   default confluence BUY vote expression (reuses the same namespace)
    vote_sell str   default confluence SELL vote expression

Adding a brand-new indicator = add its function under indicators/ and one entry here.
No edits to backtest/strategy.py or alerts/signals.py required.
"""

from stonkslib.indicators.rsi import rsi as _rsi
from stonkslib.indicators.macd import macd as _macd
from stonkslib.indicators.bollinger import bollinger_bands as _bollinger
from stonkslib.indicators.moving_avg_double import moving_averages as _ma_double
from stonkslib.indicators.supertrend import supertrend as _supertrend
from stonkslib.indicators.rsi_divergence import rsi_divergence as _rsi_div
from stonkslib.indicators.markov import markov_signals as _markov
from stonkslib.indicators.news_sentiment import news_sentiment as _news_sentiment


INDICATORS = {
    "rsi": {
        "fn": _rsi,
        "needs": ["Close"],
        "params": {"period": ("period", 14)},
        "outputs": {"rsi": None},
        "vote_buy": "rsi < 30",
        "vote_sell": "rsi > 70",
    },
    "macd": {
        "fn": _macd,
        "needs": ["Close"],
        "params": {
            "short": ("short_window", 12),
            "long": ("long_window", 26),
            "signal": ("signal_window", 9),
        },
        "outputs": {"macd": "MACD", "macd_signal": "Signal_Line"},
        "vote_buy": "crossover(macd, macd_signal)",
        "vote_sell": "crossunder(macd, macd_signal)",
    },
    "bollinger": {
        "fn": _bollinger,
        "needs": ["Close"],
        "params": {"window": ("window", 20), "num_std_dev": ("num_std_dev", 2)},
        "outputs": {"bb_upper": "Upper_Band", "bb_lower": "Lower_Band", "bb_mid": "MA"},
        "vote_buy": "close < bb_lower",
        "vote_sell": "close > bb_upper",
    },
    "ma_double": {
        "fn": _ma_double,
        "needs": ["Close"],
        "params": {"swing": ("swing_window", 20), "long": ("long_window", 50)},
        "outputs": {"ma_swing": "MA_Swing", "ma_long": "MA_Long"},
        "vote_buy": "crossover(ma_swing, ma_long)",
        "vote_sell": "crossunder(ma_swing, ma_long)",
    },
    "supertrend": {
        "fn": _supertrend,
        "needs": ["High", "Low", "Close"],
        "params": {"period": ("period", 10), "multiplier": ("multiplier", 3.0)},
        "outputs": {"st": "Supertrend", "st_dir": "Direction"},
        "vote_buy": "crossover(st_dir, 0)",
        "vote_sell": "crossunder(st_dir, 0)",
    },
    "rsi_divergence": {
        "fn": _rsi_div,
        "needs": ["Close"],
        "params": {"period": ("period", 14), "lookback": ("lookback", 20)},
        "outputs": {"bull_div": "Bullish_Divergence", "bear_div": "Bearish_Divergence", "rsi_div": "RSI"},
        "vote_buy": "bull_div",
        "vote_sell": "bear_div",
    },
    "markov": {
        "fn": _markov,
        "needs": ["Close"],
        "params": {"states": ("states", 3), "lookback": ("lookback", 60)},
        "outputs": {"mk_state": "state", "mk_bull": "bull_prob", "mk_bear": "bear_prob"},
        "vote_buy": "mk_bull > 0.6",
        "vote_sell": "mk_bear > 0.6",
    },
    "news_sentiment": {
        # LLM-scored daily news sentiment (1-10), precomputed by sentiment.scorer and
        # read from the news store — never calls the LLM at compute time. Needs the
        # ticker, which it reads from df.attrs (set in utils/load_td.load_td).
        "fn": _news_sentiment,
        "needs": ["Close"],
        "params": {"lookback": ("lookback", 1), "shift": ("shift", 1)},
        "outputs": {"news_sent": None},
        "vote_buy": "news_sent > 6",
        "vote_sell": "news_sent < 4",
    },
}

# Price columns always available in the expression namespace (lowercased aliases).
PRICE_OUTPUTS = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}


def known_names() -> set[str]:
    """Every name an expression may legally reference (price + all indicator outputs)."""
    names = set(PRICE_OUTPUTS)
    for spec in INDICATORS.values():
        names.update(spec["outputs"])
    return names
