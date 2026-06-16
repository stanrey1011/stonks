import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta

from stonkslib.dash.common import (
    load_watchlist, flat_tickers, load_ticker_data,
    MERGED_DIR, SIGNALS_DIR, STRATEGY_DIR, INTERVALS,
)
from stonkslib.utils.active_strategies import active_strategy_names

st.set_page_config(page_title="Confluence — Stonks", layout="wide")
st.title("Signal Confluence")
st.caption("Shows how many indicators agree on a BUY or SELL for each date. Higher agreement = higher conviction. Click any row in the table to overlay those indicators on the chart and draw a vertical line at that date. Use sidebar filters to narrow by strategy, direction, or minimum signal count.")

# ── constants ─────────────────────────────────────────────────────────────────

_BUY_KEYWORDS  = ("bullish", "above", "rising", "oversold")
_SELL_KEYWORDS = ("bearish", "below", "falling", "overbought")

_SIGNAL_LABELS = {
    "bollinger_signals_Signal": "Bollinger",
    "fibonacci_Signal":         "Fibonacci",
    "ma_double_signals_Signal": "MA Double",
    "ma_triple_signals_Signal": "MA Triple",
    "macd_signals_Signal":      "MACD",
    "obv_signals_Signal":       "OBV",
    "rsi_14_signals_Signal":    "RSI 14",
    "rsi_5_signals_Signal":     "RSI 5",
    "rsi_7_signals_Signal":     "RSI 7",
    "Markov":                   "Markov",   # injected live — not from merged CSV
}

# maps label → (price_overlay_csv, [cols_to_plot], signals_csv)
_INDICATOR_META = {
    "Bollinger":  ("bollinger.csv",    ["BB_upper_20_2", "BB_lower_20_2"], "bollinger_signals.csv"),
    "MA Double":  ("ma_double.csv",    ["MA_Swing", "MA_Long"],            "ma_double_signals.csv"),
    "MA Triple":  ("ma_triple.csv",    ["MA_Short", "MA_Medium", "MA_Long"], "ma_triple_signals.csv"),
    "MACD":       ("macd.csv",         ["MACD_12_26_9"],                   "macd_signals.csv"),
    "RSI 14":     ("rsi_14.csv",       ["RSI_14"],                         "rsi_14_signals.csv"),
    "OBV":        ("obv.csv",          ["OBV"],                            "obv_signals.csv"),
}

# price-chart overlays vs subplot-only
_PRICE_OVERLAYS   = {"Bollinger", "MA Double", "MA Triple"}
_SUBPLOT_OVERLAYS = {"RSI 14", "MACD", "OBV", "Markov"}

_COLORS = {
    "Bollinger":  ["#ce93d8", "#7b1fa2"],
    "MA Double":  ["#ffb74d", "#e65100"],
    "MA Triple":  ["#4fc3f7", "#0288d1", "#01579b"],
    "MACD":       ["#fff176"],
    "RSI 14":     ["#a5d6a7"],
    "OBV":        ["#80cbc4"],
    "Markov":     ["#26a69a", "#ef5350"],  # bull / bear
}

# per-strategy marker colors: (buy, sell)
_MARKER_COLORS = {
    "Bollinger":  ("#ce93d8", "#7b1fa2"),  # purple  light / dark
    "MA Double":  ("#ffb74d", "#e65100"),  # orange  light / dark
    "MA Triple":  ("#4fc3f7", "#01579b"),  # blue    light / dark
    "MACD":       ("#fff176", "#f9a825"),  # yellow  light / amber
    "RSI 14":     ("#a5d6a7", "#2e7d32"),  # green   light / dark
    "OBV":        ("#80cbc4", "#00695c"),  # teal    light / dark
    "Fibonacci":  ("#ffcc80", "#bf360c"),  # peach   light / deep-orange
    "Markov":     ("#26a69a", "#ef5350"),  # teal / red
}


# Maps a Confluence-page indicator label to the strategy-YAML confluence weight key.
# Used when saving tuned weights back into an optimized strategy YAML.
_LABEL_TO_KEY = {
    "Bollinger": "bollinger",
    "MACD":      "macd",
    "MA Double": "ma_double",
    "RSI 14":    "rsi",
    "RSI 7":     "rsi",
    "RSI 5":     "rsi",
    "Markov":    "markov",
}


def _save_confluence_yaml(base_stem: str, ticker: str, weights: dict, min_score: float) -> Path:
    """Write tuned confluence weights/min_score into a per-ticker optimized YAML.

    Loads the base strategy, merges the tuned `confluence` block, and writes
    optimized/{base}_{ticker}_optimized.yaml — matching the resolver fallback chain
    so `stonks alert`/`backtest` pick it up automatically.
    """
    import yaml
    base_path = STRATEGY_DIR / f"{base_stem}.yaml"
    strat = yaml.safe_load(base_path.read_text()) if base_path.exists() else {}
    conf = strat.get("confluence", {}) or {}
    merged = dict(conf.get("weights", {}) or {})
    merged.update({k: round(float(v), 2) for k, v in weights.items()})
    strat["confluence"] = {"min_score": round(float(min_score), 2), "weights": merged}
    out_dir = STRATEGY_DIR / "optimized"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{base_stem}_{ticker}_optimized.yaml"
    out_path.write_text(yaml.safe_dump(strat, sort_keys=False))
    return out_path


# ── helpers ───────────────────────────────────────────────────────────────────

_BUY_PAT  = "|".join(_BUY_KEYWORDS)
_SELL_PAT = "|".join(_SELL_KEYWORDS)


def _tz_align(df, interval):
    if df is None or df.empty:
        return df
    target = "US/Eastern" if interval in ("1m", "2m", "5m", "15m", "30m", "1h") else "UTC"
    if df.index.tz is None:
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(target)
    else:
        df.index = df.index.tz_convert(target)
    return df


@st.cache_resource(show_spinner=False)
def _load_csv_cached(path_str: str, interval: str) -> pd.DataFrame | None:
    path = Path(path_str)
    if not path.exists():
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df = _tz_align(df, interval)
    return df[~df.index.duplicated(keep="last")]


def _load_csv(path, interval, ref_index=None):
    df = _load_csv_cached(str(path), interval)
    if df is None:
        return None
    if ref_index is not None:
        clean_ref = ref_index[~ref_index.duplicated(keep="last")]
        df = df.reindex(clean_ref)
    return df


@st.cache_resource(show_spinner=False)
def _load_confluence_cached(ticker: str, interval: str) -> pd.DataFrame | None:
    """Vectorized confluence score computation — cached by (ticker, interval)."""
    path = MERGED_DIR / ticker / f"{interval}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df = _tz_align(df, interval)
    sig_cols = [c for c in df.columns if c in _SIGNAL_LABELS]
    if not sig_cols:
        return None

    # Vectorized: classify all cells at once with str.contains
    buy_mask  = df[sig_cols].apply(lambda s: s.str.contains(_BUY_PAT,  case=False, na=False))
    sell_mask = df[sig_cols].apply(lambda s: s.str.contains(_SELL_PAT, case=False, na=False))

    result = pd.DataFrame(index=df.index)
    result["buy"]   = buy_mask.sum(axis=1)
    result["sell"]  = sell_mask.sum(axis=1)
    result["net"]   = result["buy"] - result["sell"]
    result["close"] = df.get("Close")

    for col in sig_cols:
        label = _SIGNAL_LABELS[col]
        result[label] = ""
        result.loc[buy_mask[col],  label] = "BUY"
        result.loc[sell_mask[col], label] = "SELL"

    return result[~result.index.duplicated(keep="last")]


def _markov_params(ticker: str) -> dict:
    """Load markov params from per-ticker optimized YAML, falling back to base."""
    import yaml
    defaults = {"states": 3, "lookback": 60, "bull_threshold": 0.5, "bear_threshold": 0.5}
    for candidate in [
        STRATEGY_DIR / "optimized" / f"markov_{ticker}_optimized.yaml",
        STRATEGY_DIR / "optimized" / "markov_optimized.yaml",
        STRATEGY_DIR / "markov.yaml",
    ]:
        if candidate.exists():
            p = yaml.safe_load(candidate.read_text()).get("indicators", {}).get("markov", {}).get("params", {})
            return {**defaults, **p}
    return defaults


@st.cache_data(ttl=3600, show_spinner=False)
def _get_markov_conf(ticker: str, interval: str, states: int, lookback: int,
                     bull_thr: float, bear_thr: float) -> pd.Series:
    """Returns a Series indexed like price data with values 'BUY', 'SELL', or ''."""
    from stonkslib.indicators.markov import markov_signals
    df = load_ticker_data(ticker, interval)
    mk = markov_signals(df.copy(), states=states, lookback=lookback)
    result = pd.Series("", index=mk.index, dtype=str)
    result[mk["bull_prob"] > bull_thr] = "BUY"
    result[mk["bear_prob"] > bear_thr] = "SELL"
    return result


def _add_overlay(fig, ticker, interval, label, price_index, row, col, colors):
    sig_dir = SIGNALS_DIR / ticker / interval
    meta = _INDICATOR_META.get(label)
    if not meta:
        return
    overlay_file, overlay_cols, sig_file = meta

    # indicator lines
    odf = _load_csv(sig_dir / overlay_file, interval, price_index)
    if odf is not None:
        for i, c in enumerate(overlay_cols):
            if c not in odf.columns:
                continue
            color = colors[i % len(colors)]
            fig.add_trace(go.Scatter(
                x=odf.index, y=odf[c],
                mode="lines", name=f"{label} {c}",
                line=dict(width=1, color=color,
                          dash="dot" if label == "Bollinger" else "solid"),
                opacity=0.8,
            ), row=row, col=col)

    # signal markers on price chart (row 1 only)
    if row == 1:
        sdf = _load_csv(sig_dir / sig_file, interval, price_index)
        if sdf is not None and "Signal" in sdf.columns:
            buy_mask  = sdf["Signal"].str.contains("|".join(_BUY_KEYWORDS),  case=False, na=False)
            sell_mask = sdf["Signal"].str.contains("|".join(_SELL_KEYWORDS), case=False, na=False)

            buy_idx  = sdf[buy_mask].index
            sell_idx = sdf[sell_mask].index

            if hasattr(price_index, "to_frame"):
                price_df_ref = price_index
            else:
                price_df_ref = None

            # try to get Low/High from the loaded price df (passed via closure — use odf's Close as fallback)
            def _price_at(idx, col_name, fallback_mult):
                try:
                    return _price_ref.loc[_price_ref.index.isin(idx), col_name] * fallback_mult
                except Exception:
                    return None

            if buy_idx.any() if hasattr(buy_idx, "any") else len(buy_idx):
                fig.add_trace(go.Scatter(
                    x=buy_idx, y=[None] * len(buy_idx),  # y filled below
                    mode="markers",
                    name=f"{label} BUY",
                    marker=dict(symbol="triangle-up", size=10, color="#00e676"),
                    showlegend=True,
                ), row=1, col=1)

            if sell_idx.any() if hasattr(sell_idx, "any") else len(sell_idx):
                fig.add_trace(go.Scatter(
                    x=sell_idx, y=[None] * len(sell_idx),
                    mode="markers",
                    name=f"{label} SELL",
                    marker=dict(symbol="triangle-down", size=10, color="#ff1744"),
                    showlegend=True,
                ), row=1, col=1)


def _add_markers(fig, ticker, interval, label, price_df):
    sig_dir = SIGNALS_DIR / ticker / interval
    meta = _INDICATOR_META.get(label)
    if not meta:
        return
    _, _, sig_file = meta
    sdf = _load_csv(sig_dir / sig_file, interval, price_df.index)
    if sdf is None or "Signal" not in sdf.columns:
        return

    buy_mask  = sdf["Signal"].str.contains("|".join(_BUY_KEYWORDS),  case=False, na=False)
    sell_mask = sdf["Signal"].str.contains("|".join(_SELL_KEYWORDS), case=False, na=False)

    buy_dates  = sdf[buy_mask].index
    sell_dates = sdf[sell_mask].index

    buy_color, sell_color = _MARKER_COLORS.get(label, ("#00e676", "#ff1744"))

    if len(buy_dates):
        y_buy = price_df.loc[price_df.index.isin(buy_dates), "Low"] * 0.988
        fig.add_trace(go.Scatter(
            x=y_buy.index, y=y_buy.values,
            mode="markers", name=f"{label} ▲",
            marker=dict(symbol="triangle-up", size=10, color=buy_color,
                        line=dict(width=1, color="rgba(0,0,0,0.4)")),
        ), row=1, col=1)

    if len(sell_dates):
        y_sell = price_df.loc[price_df.index.isin(sell_dates), "High"] * 1.012
        fig.add_trace(go.Scatter(
            x=y_sell.index, y=y_sell.values,
            mode="markers", name=f"{label} ▼",
            marker=dict(symbol="triangle-down", size=10, color=sell_color,
                        line=dict(width=1, color="rgba(0,0,0,0.4)")),
        ), row=1, col=1)


# ── selectors ─────────────────────────────────────────────────────────────────

wl = load_watchlist()
tickers = flat_tickers(wl)
if not tickers:
    st.warning("No tickers in watchlist.")
    st.stop()

col1, col2 = st.columns([3, 1])
with col1:
    ticker = st.selectbox("Ticker", tickers, key="conf_ticker")
with col2:
    interval = st.selectbox("Interval", ["1d", "1wk"], key="conf_interval")

with st.sidebar:
    overlay_options = list(_INDICATOR_META.keys())
    selected_overlays = st.multiselect("Overlays", overlay_options, default=[], key="conf_overlays")

    _default_lookback = 104 if interval == "1wk" else 504
    lookback    = st.slider("Lookback (bars)", 30, 500, _default_lookback, key="conf_lookback")
    min_signals = st.slider("Min signals highlight", 1, 8, 2, key="conf_min_signals")
    show_table  = st.checkbox("Show signal table", value=True, key="conf_show_table")

    _sb1, _sb2 = st.columns(2)
    tbl_min_buy  = _sb1.number_input("Min buys",  min_value=0, max_value=10, value=0, step=1, key="conf_min_buy")
    tbl_min_sell = _sb2.number_input("Min sells", min_value=0, max_value=10, value=0, step=1, key="conf_min_sell")
    tbl_dir = st.radio("Direction", ["All", "BUY only", "SELL only"], horizontal=True, key="conf_dir")

    _all_strategy_labels = list(_SIGNAL_LABELS.values())
    active_strategies = st.multiselect(
        "Active strategies",
        options=_all_strategy_labels,
        default=_all_strategy_labels,
        key="conf_active_strats",
    )

    # ── weighted confluence tuning ────────────────────────────────────────────
    with st.expander("⚙️ Confluence tuning (weighted)", expanded=False):
        use_weighted = st.checkbox(
            "Use weighted confluence", value=False, key="conf_use_weighted",
            help="Score each agreeing indicator by a tunable weight instead of a plain "
                 "count. Bands and metrics below react live as you drag.",
        )
        conf_weights = {}
        for lbl in active_strategies:
            conf_weights[lbl] = st.slider(
                f"{lbl} weight", 0.0, 3.0, 1.0, 0.1, key=f"conf_w_{lbl}",
            )
        _max_score = round(sum(conf_weights.values()), 1) or 1.0
        weighted_min_score = st.slider(
            "Min score (highlight)", 0.0, float(_max_score), min(2.0, float(_max_score)), 0.1,
            key="conf_weighted_min_score",
        )

# ── load data ─────────────────────────────────────────────────────────────────

price_df = load_ticker_data(ticker, interval)
if price_df is None:
    st.error(f"No price data for **{ticker}** ({interval}). Run: `stonks pipeline {ticker}`")
    st.stop()

price_df = price_df[~price_df.index.duplicated(keep="last")].iloc[-lookback:]

conf_full = _load_confluence_cached(ticker, interval)
if conf_full is None:
    st.error(f"No merged data for **{ticker}** ({interval}). Run: `stonks pipeline {ticker}`")
    st.stop()

# Slice to lookback and align to price index
conf = conf_full.iloc[-lookback:] if len(conf_full) > lookback else conf_full.copy()
conf = conf.reindex(price_df.index)

# Inject Markov signals (computed live — not in merged CSV)
_mp = _markov_params(ticker)
_mk_series = _get_markov_conf(ticker, interval,
                               _mp["states"], _mp["lookback"],
                               _mp["bull_threshold"], _mp["bear_threshold"])
conf = conf.copy()
conf["Markov"] = _mk_series.reindex(conf.index).fillna("")

# ── apply strategy filter → recompute buy/sell/net ───────────────────────────

all_label_cols = list(_SIGNAL_LABELS.values())
label_cols     = [c for c in all_label_cols if c in conf.columns]

active_label_cols = [c for c in label_cols if c in active_strategies]
if active_label_cols:
    conf["buy"]  = (conf[active_label_cols] == "BUY").sum(axis=1)
    conf["sell"] = (conf[active_label_cols] == "SELL").sum(axis=1)
    conf["net"]  = conf["buy"] - conf["sell"]

# Weighted confluence: each agreeing indicator contributes its tunable weight.
conf["score_buy"]  = 0.0
conf["score_sell"] = 0.0
if use_weighted and active_label_cols:
    for c in active_label_cols:
        w = float(conf_weights.get(c, 1.0))
        conf["score_buy"]  += (conf[c] == "BUY")  * w
        conf["score_sell"] += (conf[c] == "SELL") * w

# Unified conviction masks — weighted score gate, or plain count, depending on mode.
if use_weighted:
    buy_conv  = conf["score_buy"]  >= weighted_min_score
    sell_conv = conf["score_sell"] >= weighted_min_score
    _conv_help = f"weighted score ≥ {weighted_min_score:g}"
else:
    buy_conv  = conf["buy"]  >= min_signals
    sell_conv = conf["sell"] >= min_signals
    _conv_help = f"≥ {min_signals} agreeing"

# ── row selection from table ──────────────────────────────────────────────────

label_cols = active_label_cols  # table only shows selected strategies

mask = (conf["buy"] >= tbl_min_buy) & (conf["sell"] >= tbl_min_sell)
if tbl_dir == "BUY only":
    mask &= conf["buy"] > 0
elif tbl_dir == "SELL only":
    mask &= conf["sell"] > 0
else:
    mask &= (conf["buy"] > 0) | (conf["sell"] > 0)

display_data = conf[mask].copy()
display_data = display_data.sort_index(ascending=False)

selected_dates = []
auto_overlays  = []

if show_table:
    st.subheader("Signal breakdown — select rows to overlay on chart")
    display_show = display_data[["buy", "sell", "net"] + label_cols].copy()
    display_show.index = display_show.index.strftime("%Y-%m-%d")
    display_show.columns = ["Buy", "Sell", "Net"] + label_cols

    event = st.dataframe(
        display_show,
        use_container_width=True,
        selection_mode="multi-row",
        on_select="rerun",
        key="conf_table",
    )

    if event.selection and event.selection.rows:
        selected_dates = [display_data.index[i] for i in event.selection.rows]
        for i in event.selection.rows:
            row_data = display_data.iloc[i]
            for lbl in label_cols:
                if lbl in _INDICATOR_META and row_data.get(lbl) in ("BUY", "SELL"):
                    auto_overlays.append(lbl)
        auto_overlays = list(dict.fromkeys(auto_overlays))  # dedupe, preserve order
        date_strs = ", ".join(d.strftime("%Y-%m-%d") for d in selected_dates)
        st.caption(
            f"Selected {len(selected_dates)} row(s): **{date_strs}** — "
            f"overlaying: {', '.join(auto_overlays) if auto_overlays else 'none'}"
        )

active_overlays = list(dict.fromkeys(selected_overlays + auto_overlays))

# ── summary metrics ───────────────────────────────────────────────────────────

m1, m2, m3, m4 = st.columns(4)
if use_weighted:
    m1.metric("Latest BUY score",  f"{conf['score_buy'].iloc[-1]:g}")
    m2.metric("Latest SELL score", f"{conf['score_sell'].iloc[-1]:g}")
else:
    m1.metric("Latest buy signals",  conf["buy"].iloc[-1])
    m2.metric("Latest sell signals", conf["sell"].iloc[-1])
m3.metric("High-conviction BUY days",  int(buy_conv.sum()),  help=f"Days with {_conv_help} bullish")
m4.metric("High-conviction SELL days", int(sell_conv.sum()), help=f"Days with {_conv_help} bearish")

# ── tuning quality feedback + save ────────────────────────────────────────────
# Forward-return after high-conviction BUY days reacts live to weight/min_score
# tuning — a fast proxy for "is this confluence spotting good entries?". (Note:
# the equity backtest itself doesn't gate on confluence — that's an alert/scan
# concept — so this forward-return readout is the meaningful live signal here.)
if use_weighted:
    _h = 5 if interval == "1wk" else 10
    _fwd = price_df["Close"].pct_change(_h).shift(-_h)
    _buy_days = conf.index[buy_conv.reindex(conf.index, fill_value=False)]
    _avg_buy = _fwd.reindex(_buy_days).dropna()
    _baseline = _fwd.dropna().mean()
    q1, q2 = st.columns(2)
    if len(_avg_buy):
        q1.metric(
            f"Avg {_h}-bar fwd return after BUY", f"{_avg_buy.mean():+.2%}",
            delta=f"{(_avg_buy.mean() - _baseline):+.2%} vs baseline",
            help="Mean forward return following high-conviction BUY days. Tune weights/"
                 "min-score to push this above the all-days baseline.",
        )
    else:
        q1.metric(f"Avg {_h}-bar fwd return after BUY", "—",
                  help="No high-conviction BUY days at this min-score.")
    q2.metric("All-days baseline", f"{_baseline:+.2%}")

    with st.expander("💾 Save tuned weights to an optimized strategy YAML", expanded=False):
        _active_names = active_strategy_names()
        base_stem = st.selectbox(
            "Apply to base strategy", _active_names, key="conf_save_base",
            help="Tuned weights + min-score are written to "
                 "optimized/{strategy}_{ticker}_optimized.yaml, picked up automatically "
                 "by alert/backtest via the resolver fallback chain.",
        )
        # Aggregate page-label weights into strategy confluence keys (max wins on collisions).
        key_weights = {}
        for lbl, w in conf_weights.items():
            key = _LABEL_TO_KEY.get(lbl)
            if key:
                key_weights[key] = max(key_weights.get(key, 0.0), float(w))
        st.caption(f"Maps to keys: {key_weights or '(none of the active labels map to a strategy key)'}")
        if st.button("Save as optimized YAML", type="primary", key="conf_save_btn"):
            if not key_weights:
                st.warning("None of the selected indicators map to a strategy confluence key.")
            else:
                out = _save_confluence_yaml(base_stem, ticker, key_weights, weighted_min_score)
                st.success(f"Saved → {out.relative_to(STRATEGY_DIR.parents[1])}")

# ── build chart ───────────────────────────────────────────────────────────────

show_sub   = any(o in _SUBPLOT_OVERLAYS for o in active_overlays)
n_rows     = 3 if show_sub else 2
row_heights = [0.50, 0.25, 0.25] if show_sub else [0.65, 0.35]
subplot_titles = ["Price", "Confluence", "Indicators"] if show_sub else ["Price", "Confluence"]

fig = make_subplots(
    rows=n_rows, cols=1,
    shared_xaxes=True,
    row_heights=row_heights,
    vertical_spacing=0.03,
    subplot_titles=subplot_titles,
)

# candlestick
fig.add_trace(go.Candlestick(
    x=price_df.index,
    open=price_df["Open"], high=price_df["High"],
    low=price_df["Low"],   close=price_df["Close"],
    name="Price",
    increasing_line_color="#26a69a",
    decreasing_line_color="#ef5350",
), row=1, col=1)

# confluence bars
colors_bar = ["#26a69a" if n >= 0 else "#ef5350" for n in conf["net"]]
fig.add_trace(go.Bar(
    x=conf.index, y=conf["net"],
    name="Net confluence",
    marker_color=colors_bar, opacity=0.85,
), row=2, col=1)
fig.add_hline(y=0, line_width=1, line_color="rgba(255,255,255,0.2)", row=2, col=1)

# high-conviction background bands — batch all shapes in one update_layout call
# (looping add_vrect is O(n²) in Plotly; batching is dramatically faster)
half_bar = timedelta(days=3) if interval == "1wk" else timedelta(hours=14)
_shapes = []
for d in conf[buy_conv].index:
    _shapes.append(dict(
        type="rect", xref="x", yref="paper",
        x0=d - half_bar, x1=d + half_bar, y0=0, y1=1,
        fillcolor="rgba(38,166,154,0.10)", line_width=0, layer="below",
    ))
for d in conf[sell_conv].index:
    _shapes.append(dict(
        type="rect", xref="x", yref="paper",
        x0=d - half_bar, x1=d + half_bar, y0=0, y1=1,
        fillcolor="rgba(239,83,80,0.10)", line_width=0, layer="below",
    ))
if _shapes:
    fig.update_layout(shapes=_shapes)

# price overlays + signal markers
for label in active_overlays:
    colors = _COLORS.get(label, ["#90caf9"])
    if label in _PRICE_OVERLAYS:
        sig_dir = SIGNALS_DIR / ticker / interval
        meta = _INDICATOR_META[label]
        odf = _load_csv(sig_dir / meta[0], interval, price_df.index)
        if odf is not None:
            for i, c in enumerate(meta[1]):
                if c not in odf.columns:
                    continue
                fig.add_trace(go.Scatter(
                    x=odf.index, y=odf[c],
                    mode="lines", name=f"{label} ({c})",
                    line=dict(width=1, color=colors[i % len(colors)],
                              dash="dot" if label == "Bollinger" else "solid"),
                    opacity=0.85,
                ), row=1, col=1)
        _add_markers(fig, ticker, interval, label, price_df)

    elif label in _SUBPLOT_OVERLAYS and show_sub:
        sig_dir = SIGNALS_DIR / ticker / interval
        meta = _INDICATOR_META[label]
        odf = _load_csv(sig_dir / meta[0], interval, price_df.index)
        if odf is not None:
            for i, c in enumerate(meta[1]):
                if c not in odf.columns:
                    continue
                fig.add_trace(go.Scatter(
                    x=odf.index, y=odf[c],
                    mode="lines", name=f"{label}",
                    line=dict(width=1, color=colors[i % len(colors)]),
                ), row=3, col=1)
        if label == "RSI 14":
            fig.add_hline(y=70, line_dash="dot", line_color="rgba(239,83,80,0.5)",  row=3, col=1)
            fig.add_hline(y=30, line_dash="dot", line_color="rgba(38,166,154,0.5)", row=3, col=1)
        _add_markers(fig, ticker, interval, label, price_df)

    elif label == "Markov" and show_sub:
        from stonkslib.indicators.markov import markov_signals
        mk = markov_signals(load_ticker_data(ticker, interval).copy(),
                            states=_mp["states"], lookback=_mp["lookback"]).iloc[-lookback:]
        fig.add_trace(go.Scatter(
            x=mk.index, y=mk["bull_prob"],
            mode="lines", name="Markov bull",
            line=dict(width=1.5, color="#26a69a"),
        ), row=3, col=1)
        fig.add_trace(go.Scatter(
            x=mk.index, y=mk["bear_prob"],
            mode="lines", name="Markov bear",
            line=dict(width=1.5, color="#ef5350"),
        ), row=3, col=1)
        fig.add_hline(y=_mp["bull_threshold"], line_dash="dot",
                      line_color="rgba(38,166,154,0.5)", row=3, col=1)
        fig.add_hline(y=_mp["bear_threshold"], line_dash="dot",
                      line_color="rgba(239,83,80,0.5)",  row=3, col=1)
        # markers on price chart
        buy_mask  = mk["bull_prob"] > _mp["bull_threshold"]
        sell_mask = mk["bear_prob"] > _mp["bear_threshold"]
        if buy_mask.any():
            y = price_df["Low"].reindex(mk.index[buy_mask]) * 0.988
            fig.add_trace(go.Scatter(
                x=y.index, y=y.values, mode="markers", name="Markov ▲",
                marker=dict(symbol="triangle-up", size=10, color="#26a69a",
                            line=dict(width=1, color="rgba(0,0,0,0.4)")),
            ), row=1, col=1)
        if sell_mask.any():
            y = price_df["High"].reindex(mk.index[sell_mask]) * 1.012
            fig.add_trace(go.Scatter(
                x=y.index, y=y.values, mode="markers", name="Markov ▼",
                marker=dict(symbol="triangle-down", size=10, color="#ef5350",
                            line=dict(width=1, color="rgba(0,0,0,0.4)")),
            ), row=1, col=1)
        fig.update_yaxes(range=[0, 1], row=3, col=1)

# selected dates: vertical lines + annotations
for selected_date in selected_dates:
    for r in range(1, n_rows + 1):
        fig.add_vline(
            x=selected_date,
            line_width=1.5, line_dash="dash",
            line_color="rgba(255,255,255,0.6)",
            row=r, col=1,
        )
    close_val = price_df.iloc[price_df.index.get_indexer([selected_date], method="nearest")[0]]["Close"]
    fig.add_annotation(
        x=selected_date, y=close_val,
        text=selected_date.strftime("%b %d"),
        showarrow=True, arrowhead=2,
        font=dict(color="white", size=11),
        bgcolor="rgba(50,50,50,0.7)",
        row=1, col=1,
    )

# layout
fig.update_layout(
    height=720 if show_sub else 620,
    xaxis_rangeslider_visible=False,
    margin=dict(l=0, r=0, t=40, b=0),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=11)),
)
fig.update_yaxes(title_text="Net signals", row=2, col=1)
if show_sub:
    fig.update_yaxes(title_text="Value", row=3, col=1)

if interval in ("1d", "1wk"):
    for r in range(1, n_rows + 1):
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], row=r, col=1)

st.plotly_chart(fig, use_container_width=True)
