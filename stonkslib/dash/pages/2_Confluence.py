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
    MERGED_DIR, SIGNALS_DIR, INTERVALS,
)

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
_SUBPLOT_OVERLAYS = {"RSI 14", "MACD", "OBV"}

_COLORS = {
    "Bollinger":  ["#ce93d8", "#7b1fa2"],
    "MA Double":  ["#ffb74d", "#e65100"],
    "MA Triple":  ["#4fc3f7", "#0288d1", "#01579b"],
    "MACD":       ["#fff176"],
    "RSI 14":     ["#a5d6a7"],
    "OBV":        ["#80cbc4"],
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
}


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

# ── apply strategy filter → recompute buy/sell/net ───────────────────────────

all_label_cols = list(_SIGNAL_LABELS.values())
label_cols     = [c for c in all_label_cols if c in conf.columns]

active_label_cols = [c for c in label_cols if c in active_strategies]
if active_label_cols:
    conf["buy"]  = (conf[active_label_cols] == "BUY").sum(axis=1)
    conf["sell"] = (conf[active_label_cols] == "SELL").sum(axis=1)
    conf["net"]  = conf["buy"] - conf["sell"]

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
m1.metric("Latest buy signals",       conf["buy"].iloc[-1])
m2.metric("Latest sell signals",      conf["sell"].iloc[-1])
m3.metric("High-conviction BUY days", (conf["buy"]  >= min_signals).sum(),
          help=f"Days with ≥{min_signals} bullish signals")
m4.metric("High-conviction SELL days",(conf["sell"] >= min_signals).sum(),
          help=f"Days with ≥{min_signals} bearish signals")

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
for d in conf[conf["buy"] >= min_signals].index:
    _shapes.append(dict(
        type="rect", xref="x", yref="paper",
        x0=d - half_bar, x1=d + half_bar, y0=0, y1=1,
        fillcolor="rgba(38,166,154,0.10)", line_width=0, layer="below",
    ))
for d in conf[conf["sell"] >= min_signals].index:
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
