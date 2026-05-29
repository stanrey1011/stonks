import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json

from stonkslib.dash.common import (
    load_watchlist, flat_tickers, load_ticker_data,
    STRATEGY_DIR, BACKTEST_DIR, CLEAN_DIR,
)

st.set_page_config(page_title="Backtest — Stonks", layout="wide")
st.title("Backtest")
st.caption("Tests every strategy against historical price data for a ticker and ranks them by a composite confidence score. Compares indicator-based exits vs a trailing stop side by side. Adjust the date window and trailing stop % in the sidebar. Higher score = better balance of return, win rate, and drawdown.")

wl = load_watchlist()
tickers = flat_tickers(wl)
if not tickers:
    st.warning("No tickers in watchlist.")
    st.stop()

# ── selectors ─────────────────────────────────────────────────────────────────

col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    ticker = st.selectbox("Ticker", tickers, key="bt_ticker")
with col2:
    interval = st.selectbox("Interval", ["1d", "1wk"], key="bt_interval")
with col3:
    st.write("")
    st.write("")
    run = st.button("Run Backtest", type="primary", use_container_width=True)

# ── date range ────────────────────────────────────────────────────────────────

_df_full = load_ticker_data(ticker, interval)
if _df_full is not None and not _df_full.empty:
    _min_date = _df_full.index[0].date()
    _max_date = _df_full.index[-1].date()
    _default_lookback = {"1wk": 260, "1d": 756, "1h": 504}.get(interval, 252)
    _default_start = _df_full.index[-min(_default_lookback, len(_df_full))].date()

    dc1, dc2 = st.columns(2)
    with dc1:
        start_date = st.date_input("From", value=_default_start,
                                   min_value=_min_date, max_value=_max_date)
    with dc2:
        end_date = st.date_input("To", value=_max_date,
                                 min_value=_min_date, max_value=_max_date)

    _window = _df_full[
        (_df_full.index.date >= start_date) &
        (_df_full.index.date <= end_date)
    ]
    st.caption(
        f"Backtest window: **{start_date.strftime('%b %d, %Y')} → "
        f"{end_date.strftime('%b %d, %Y')}** ({len(_window)} {interval} bars)"
    )
else:
    _window = None

# ── trailing stop slider ──────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("**Capital**")
    _sc1, _sc2 = st.columns(2)
    start_cash = _sc1.number_input(
        "Start ($)", min_value=100, value=10000, step=500, key="bt_start_cash",
    )
    risk_pct = _sc2.slider(
        "Alloc %", min_value=5, max_value=100, value=20, step=5, key="bt_risk_pct",
        help="% of cash used per trade signal",
    ) / 100

    st.markdown("**DCA per signal**")
    per_signal_amount = st.number_input(
        "$ per signal", min_value=0, value=0, step=50, key="bt_per_signal",
        help="Invest exactly this $ on each buy signal (orange line). 0 = use Alloc % instead.",
    )

    st.markdown("**Buy & Hold — DCA**")
    _dc1, _dc2 = st.columns(2)
    dca_amount = _dc1.number_input(
        "Add ($)", min_value=0, value=0, step=100, key="bt_dca_amount",
        help="Contribution added every N bars. 0 = one-time lump sum.",
    )
    _freq_options = {"Weekly": 5, "Bi-wk": 10, "Monthly": 21}
    if dca_amount > 0:
        dca_freq_label = _dc2.selectbox("Freq", list(_freq_options.keys()), key="bt_dca_freq")
        dca_bars = _freq_options[dca_freq_label]
        total_periods = len(_window) // dca_bars if _window is not None and len(_window) > 0 else 0
        st.caption(f"≈ {total_periods} contributions · ${dca_amount * total_periods + start_cash:,.0f} invested")
    else:
        dca_bars = 0

    st.markdown("**Exits**")
    trail_pct = st.slider(
        "Trailing stop %", min_value=5, max_value=30, value=12, step=1,
        help="Exits when price drops this % below the post-entry peak",
    )

    st.markdown("**Score weights**")
    _wc1, _wc2 = st.columns(2)
    w_return   = _wc1.slider("Return",    0, 100, 35, 5)
    w_winrate  = _wc2.slider("Win rate",  0, 100, 30, 5)
    w_pertrade = _wc1.slider("Per trade", 0, 100, 20, 5,
                             help="Rewards fewer, more profitable trades")
    w_drawdown = _wc2.slider("Drawdown",  0, 100, 15, 5,
                             help="Higher weight penalises large drawdowns")
    _total_w = w_return + w_winrate + w_pertrade + w_drawdown
    if _total_w == 0:
        st.warning("All weights are zero.")


# ── helpers ───────────────────────────────────────────────────────────────────

def _resolve_strategy(path, ticker):
    opt_dir = STRATEGY_DIR / "optimized"
    for candidate in [
        opt_dir / f"{path.stem}_{ticker}_optimized.yaml",
        opt_dir / f"{path.stem}_optimized.yaml",
    ]:
        if candidate.exists():
            return candidate
    return path


def _metrics_row(m, label):
    invested = m.get("total_invested", m.get("start_cash", 10000))
    pnl      = m.get("net_pnl", 0)
    return {
        "Exit mode":    label,
        "Net P&L":      f"${pnl:,.2f}",
        "Return":       f"{pnl/invested*100:+.1f}%" if invested else "—",
        "Win rate":     f"{m.get('win_rate', 0):.1%}",
        "Trades":       m.get("trades", 0),
        "Max drawdown": f"{m.get('max_drawdown', 0):.1%}",
        "Final cash":   f"${m.get('final_cash', invested):,.2f}",
    }


def _equity_chart(ind_m, ts_m, strat_name, bh_m=None, dca_m=None):
    fig = go.Figure()
    amt = dca_m.get("per_signal_amount", 0) if dca_m else 0
    dca_label = f"Indicator (${amt:,.0f}/signal)" if amt else "Indicator + DCA"
    for m, color, name, dash in [
        (ind_m, "#42a5f5", "Indicator exits",             "solid"),
        (ts_m,  "#66bb6a", f"Trailing stop {trail_pct}%", "solid"),
        (dca_m, "#ff9800", dca_label,                     "solid"),
        (bh_m,  "#9e9e9e", "Buy & Hold",                  "dot"),
    ]:
        if m and m.get("equity_curve"):
            eq = pd.DataFrame(m["equity_curve"])
            eq["date"] = pd.to_datetime(eq["date"])
            fig.add_trace(go.Scatter(
                x=eq["date"], y=eq["value"],
                mode="lines", name=name,
                line=dict(width=1.5 if dash == "solid" else 1, color=color, dash=dash),
            ))
    start_cash = (ind_m or ts_m or bh_m or {}).get("start_cash", 10000)
    fig.add_hline(y=start_cash, line_dash="dot",
                  line_color="rgba(255,255,255,0.2)")
    fig.update_layout(
        title=strat_name,
        height=260,
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(orientation="h", y=1.1),
        xaxis_rangeslider_visible=False,
    )
    return fig


def _confidence_score(m, all_metrics):
    """0–100 composite score. Higher = better."""
    if not m or _total_w == 0:
        return 0.0

    def _norm(val, vals, invert=False):
        lo, hi = min(vals), max(vals)
        if hi == lo:
            return 0.5
        n = (val - lo) / (hi - lo)
        return 1 - n if invert else n

    def _per_trade(x):
        t = max(x.get("trades", 0), 1)
        return x.get("net_pnl", 0) / t

    returns   = [x.get("net_pnl", 0) / max(x.get("total_invested", x.get("start_cash", 10000)), 1) for x in all_metrics]
    winrates  = [x.get("win_rate", 0) for x in all_metrics]
    drawdowns = [x.get("max_drawdown", 1) for x in all_metrics]
    pertrades = [_per_trade(x) for x in all_metrics]

    this_return   = m.get("net_pnl", 0) / max(m.get("total_invested", m.get("start_cash", 10000)), 1)
    this_pertrade = _per_trade(m)

    s = (
        w_return   * _norm(this_return,              returns)                +
        w_winrate  * _norm(m.get("win_rate", 0),     winrates)               +
        w_pertrade * _norm(this_pertrade,             pertrades)              +
        w_drawdown * _norm(m.get("max_drawdown", 1), drawdowns, invert=True)
    )
    return round(s / _total_w * 100, 1)


def _show_comparison(all_results, bh_m=None):
    """all_results: list of (strat_name, ind_metrics, ts_metrics, dca_metrics)"""
    if not all_results:
        return

    # build flat list for scoring — exclude B&H from confidence scoring
    flat = []
    for name, ind_m, ts_m, dca_m in all_results:
        if ind_m:
            flat.append((name, "Indicator", ind_m))
        if ts_m:
            flat.append((name, f"Trail {trail_pct}%", ts_m))
        if dca_m:
            amt = dca_m.get("per_signal_amount", 0)
            flat.append((name, f"${amt:,.0f}/signal" if amt else "DCA", dca_m))

    all_metrics = [m for _, _, m in flat]

    scored = sorted(
        [(name, mode, m, _confidence_score(m, all_metrics)) for name, mode, m in flat],
        key=lambda x: x[3], reverse=True,
    )

    # ── top 3 confidence leaderboard ─────────────────────────────────────────
    st.subheader("Confidence Ranking")
    medals = ["🥇", "🥈", "🥉"]
    cols = st.columns(min(3, len(scored)))
    for col, (name, mode, m, score), medal in zip(cols, scored[:3], medals):
        invested = m.get("total_invested", m.get("start_cash", 10000))
        pnl      = m.get("net_pnl", 0)
        with col:
            st.metric(
                label=f"{medal} {name}",
                value=f"{score:.0f} / 100",
                delta=f"{pnl/invested*100:+.1f}% return · {m.get('win_rate',0):.0%} win rate",
            )
            st.caption(f"Exit: {mode} · Drawdown: {m.get('max_drawdown',0):.1%} · Trades: {m.get('trades',0)}")

    st.divider()

    # ── full summary table ────────────────────────────────────────────────────
    st.subheader("All Results")
    rows = []
    for name, mode, m, score in scored:
        invested = m.get("total_invested", m.get("start_cash", 10000))
        pnl      = m.get("net_pnl", 0)
        rows.append({
            "Rank":         scored.index((name, mode, m, score)) + 1,
            "Strategy":     name,
            "Exit":         mode,
            "Score":        int(score),
            "Net P&L":      round(pnl, 2),
            "Return %":     round(pnl / invested * 100, 2) if invested else 0.0,
            "Win rate":     round(m.get("win_rate", 0) * 100, 1),
            "Trades":       m.get("trades", 0),
            "Max DD %":     round(m.get("max_drawdown", 0) * 100, 2),
            "Final cash":   round(m.get("final_cash", invested), 2),
        })

    if bh_m:
        invested = bh_m.get("total_invested", bh_m.get("start_cash", 10000))
        pnl      = bh_m.get("net_pnl", 0)
        rows.append({
            "Rank":         None,
            "Strategy":     bh_m.get("strategy", "Buy & Hold"),
            "Exit":         "Hold forever",
            "Score":        None,
            "Net P&L":      round(pnl, 2),
            "Return %":     round(pnl / invested * 100, 2) if invested else 0.0,
            "Win rate":     None,
            "Trades":       bh_m.get("trades", 1),
            "Max DD %":     round(bh_m.get("max_drawdown", 0) * 100, 2),
            "Final cash":   round(bh_m.get("final_cash", invested), 2),
        })

    col_cfg = {
        "Net P&L":    st.column_config.NumberColumn("Net P&L",    format="$%.2f"),
        "Return %":   st.column_config.NumberColumn("Return %",   format="%.2f%%"),
        "Win rate":   st.column_config.NumberColumn("Win rate",   format="%.1f%%"),
        "Max DD %":   st.column_config.NumberColumn("Max DD %",   format="%.2f%%"),
        "Final cash": st.column_config.NumberColumn("Final cash", format="$%.2f"),
    }
    st.dataframe(pd.DataFrame(rows), column_config=col_cfg, use_container_width=True, hide_index=True)

    # ── equity curves ─────────────────────────────────────────────────────────
    st.subheader("Equity curves")
    st.caption("Grey dashed = Buy & Hold benchmark · Orange = Indicator exits + DCA contributions")
    for name, ind_m, ts_m, dca_m in all_results:
        st.plotly_chart(_equity_chart(ind_m, ts_m, name, bh_m=bh_m, dca_m=dca_m), use_container_width=True)


# ── run ───────────────────────────────────────────────────────────────────────

if run:
    from stonkslib.backtest.strategy import run_strategy_backtest, load_strategy, run_buy_and_hold

    if _window is None or _window.empty:
        st.warning("No data in selected date range.")
    else:
        strategy_paths = list(STRATEGY_DIR.glob("*.yaml"))
        all_results = []

        with st.status(f"Running backtests for {ticker} ({interval})...", expanded=True) as status:
            log = st.empty()

            log.text("Running Buy & Hold benchmark...")
            bh_m = run_buy_and_hold(
                _window, start_cash=start_cash,
                dca_amount=dca_amount, dca_bars=dca_bars,
            )

            for i, path in enumerate(strategy_paths):
                active = _resolve_strategy(path, ticker)
                strat  = load_strategy(active)
                name   = strat.get("name", path.stem)
                log.text(f"[{i+1}/{len(strategy_paths)}] {name} — indicator exits...")
                ind_m = run_strategy_backtest(
                    ticker, interval, strat, df_override=_window,
                    start_cash_override=start_cash, risk_pct_override=risk_pct,
                )
                log.text(f"[{i+1}/{len(strategy_paths)}] {name} — trailing stop {trail_pct}%...")
                ts_m  = run_strategy_backtest(
                    ticker, interval, strat, df_override=_window,
                    trailing_stop_pct=trail_pct / 100,
                    start_cash_override=start_cash, risk_pct_override=risk_pct,
                )
                dca_m = None
                if per_signal_amount > 0:
                    log.text(f"[{i+1}/{len(strategy_paths)}] {name} — ${per_signal_amount}/signal...")
                    dca_m = run_strategy_backtest(
                        ticker, interval, strat, df_override=_window,
                        start_cash_override=start_cash, risk_pct_override=risk_pct,
                        per_signal_amount=per_signal_amount,
                    )

                all_results.append((name, ind_m, ts_m, dca_m))

            status.update(label=f"Done — {len(all_results)} strategies + Buy & Hold compared",
                          state="complete", expanded=False)

        _show_comparison(all_results, bh_m=bh_m)
