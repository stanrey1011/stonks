import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import subprocess
import yaml
from datetime import datetime, timezone

import streamlit as st
import pandas as pd

from stonkslib.dash.common import (
    load_watchlist, flat_tickers,
    CLEAN_DIR, STONKS_BIN, STRATEGY_DIR, VALID_CATEGORIES,
)
from stonkslib.llm import client


def _llm_models() -> list[str]:
    """Models the LLM server reports, with a sane fallback if unreachable."""
    return client.list_models() or [client.default_model()]


st.set_page_config(page_title="Pipeline — Stonks", layout="wide")
st.title("Pipeline & Operations")
st.caption("Three tabs: Data shows how fresh each ticker's price data is and lets you re-fetch it. Alerts runs a signal scan on demand with confluence filtering and optional LLM conviction scoring. Optimize uses a local AI model to tune strategy parameters — requires the LLM server to be running.")

wl = load_watchlist()
tickers = flat_tickers(wl)

strategy_files = sorted(STRATEGY_DIR.glob("*.yaml"))
strategy_names = [yaml.safe_load(p.read_text()).get("name", p.stem) for p in strategy_files]
strategy_map   = dict(zip(strategy_names, strategy_files))


# ── helpers ───────────────────────────────────────────────────────────────────

def _freshness_df(ticker_list, intervals=("1d", "1wk", "1h")):
    now = datetime.now(timezone.utc)
    rows = []
    for ticker in ticker_list:
        for iv in intervals:
            path = CLEAN_DIR / ticker / f"{iv}.parquet"
            if path.exists():
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                age_h = (now - mtime).total_seconds() / 3600
                if age_h < 24:
                    age_str = f"{age_h:.0f}h ago"
                    flag = "Fresh"
                elif age_h < 72:
                    age_str = f"{age_h / 24:.0f}d ago"
                    flag = "Stale"
                else:
                    age_str = f"{age_h / 24:.0f}d ago"
                    flag = "Old"
            else:
                age_str = "—"
                flag = "Missing"
            rows.append({"Ticker": ticker, "Interval": iv, "Last updated": age_str, "Status": flag})
    return pd.DataFrame(rows)


def _stream(cmd, status_widget, total: int = 0, step_marker: str = "[✓]"):
    """
    Run cmd, stream stdout into a code block, and optionally show a progress bar.
    total > 0 enables the bar; it advances each time step_marker appears in a line.
    """
    proc = subprocess.Popen(
        [str(c) for c in cmd],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    bar   = st.progress(0.0, text="Starting…") if total > 0 else None
    log   = st.empty()
    lines = []
    done  = 0
    for raw in proc.stdout:
        line = raw.rstrip()
        if line:
            lines.append(line)
            log.code("\n".join(lines[-30:]), language="text")
            if bar and step_marker in line:
                done += 1
                pct   = min(done / total, 1.0)
                bar.progress(pct, text=f"{done} / {total} done")
    proc.wait()
    if bar:
        bar.progress(1.0, text=f"Complete — {done} / {total}")
    return proc.returncode


# ── tabs ──────────────────────────────────────────────────────────────────────

tab_data, tab_alerts, tab_optimize = st.tabs(["Data & Pipeline", "Alerts", "Optimize"])


# ══════════════════════════════════════════════════════════════════
# DATA & PIPELINE
# ══════════════════════════════════════════════════════════════════

with tab_data:
    col_hdr, col_refresh = st.columns([6, 1])
    col_hdr.subheader("Data Freshness")
    refresh = col_refresh.button("Refresh", use_container_width=True)

    if tickers:
        _status_colors = {
            "Fresh":   "background-color:#1b5e20; color:white",
            "Stale":   "background-color:#e65100; color:white",
            "Old":     "background-color:#b71c1c; color:white",
            "Missing": "background-color:#37474f; color:white",
        }
        fresh_df = _freshness_df(tickers)
        st.dataframe(
            fresh_df.style.apply(
                lambda col: [_status_colors.get(v, "") for v in col],
                subset=["Status"],
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No tickers in watchlist. Add some on the Watchlist page.")

    st.divider()
    st.subheader("Run Pipeline")
    st.caption("Fetch → clean → analyze → merge for the selected target and intervals.")

    c1, c2 = st.columns([3, 2])
    with c1:
        pipe_target = st.selectbox(
            "Target",
            ["all"] + VALID_CATEGORIES + tickers,
            help="all, a category (stocks/etfs/crypto), or a single ticker",
            key="pipe_target",
        )
    with c2:
        pipe_intervals = st.multiselect(
            "Intervals", ["1d", "1wk", "1h"], default=["1d", "1wk"],
            key="pipe_intervals",
        )

    if st.button("Run Pipeline", type="primary", key="run_pipeline"):
        if not pipe_intervals:
            st.warning("Select at least one interval.")
        else:
            if pipe_target == "all":
                pipe_count = len(tickers)
            elif pipe_target in VALID_CATEGORIES:
                pipe_count = len(wl.get(pipe_target, []) or [])
            else:
                pipe_count = 1

            for iv in pipe_intervals:
                label = f"Pipeline — {pipe_target}  {iv}"
                with st.status(label, expanded=True) as s:
                    rc = _stream(
                        [STONKS_BIN, "pipeline", pipe_target, "--interval", iv], s,
                        total=pipe_count, step_marker="[✓]",
                    )
                    if rc == 0:
                        s.update(label=f"✓ {label}", state="complete", expanded=False)
                    else:
                        s.update(label=f"✗ {label} — check output above", state="error")


# ══════════════════════════════════════════════════════════════════
# ALERTS
# ══════════════════════════════════════════════════════════════════

with tab_alerts:
    st.subheader("Alert Scan")
    st.caption("Checks the latest bar for each ticker and optionally posts to Discord.")

    c1, c2, c3 = st.columns(3)
    with c1:
        alert_target = st.selectbox(
            "Target", ["all"] + VALID_CATEGORIES + tickers, key="alert_target",
        )
    with c2:
        alert_interval = st.selectbox(
            "Interval", ["1d", "1wk", "1h"], key="alert_interval",
        )
    with c3:
        alert_strats = st.multiselect(
            "Strategies", strategy_names, default=strategy_names, key="alert_strats",
        )

    c4, c5 = st.columns(2)
    with c4:
        min_signals = st.number_input(
            "Min signals (confluence)", min_value=1, max_value=8, value=2, step=1,
            help="How many indicators must agree before an alert fires",
        )
    with c5:
        confirm_weekly = st.checkbox(
            "Confirm with weekly trend",
            value=True,
            help="For 1d: only alert if the weekly 20/50 EMA trend agrees with signal direction",
        )

    c6, c7 = st.columns(2)
    with c6:
        llm_interpret = st.checkbox(
            "LLM conviction scoring",
            value=False,
            help="Ask the local llama.cpp model to assess each signal and add plain-English reasoning. Requires the LLM server running.",
        )
    with c7:
        llm_model_alert = st.selectbox(
            "Model", _llm_models(),
            key="alert_llm_model",
            disabled=not llm_interpret,
        )

    post_discord = st.checkbox("Post results to Discord", value=False)

    if st.button("Scan Now", type="primary", key="run_alert"):
        if not alert_strats:
            st.warning("Select at least one strategy.")
        else:
            cmd = [STONKS_BIN, "alert", alert_target, "--interval", alert_interval,
                   "--min-signals", str(min_signals)]

            if confirm_weekly and alert_interval == "1d":
                cmd.append("--confirm-weekly")

            if llm_interpret:
                cmd += ["--llm-interpret", "--llm-model", llm_model_alert]

            if set(alert_strats) == set(strategy_names):
                cmd.append("--all-strategies")
            else:
                for name in alert_strats:
                    cmd += ["--strategy", strategy_map[name].name]

            # suppress Discord by passing empty webhook when unchecked
            if not post_discord:
                cmd += ["--webhook-url", ""]

            if alert_target == "all":
                _alert_count = len(tickers)
            elif alert_target in VALID_CATEGORIES:
                _alert_count = len(wl.get(alert_target, []) or [])
            else:
                _alert_count = 1

            with st.status(f"Scanning {alert_target} — {alert_interval}...", expanded=True) as s:
                rc = _stream(cmd, s, total=_alert_count, step_marker="[✓]")
                if rc == 0:
                    s.update(label="Scan complete", state="complete", expanded=False)
                else:
                    s.update(label="Scan failed — check output above", state="error")


# ══════════════════════════════════════════════════════════════════
# OPTIMIZE
# ══════════════════════════════════════════════════════════════════

with tab_optimize:
    st.subheader("Strategy Optimizer")
    st.caption(
        "Uses the local llama.cpp LLM to iteratively tune strategy parameters. "
        "The LLM server must be running. This can take several minutes."
    )

    c1, c2 = st.columns(2)
    with c1:
        opt_strats = st.multiselect(
            "Strategies", strategy_names, default=strategy_names, key="opt_strats",
        )
    with c2:
        opt_interval = st.selectbox("Interval", ["1d", "1wk", "1h"], key="opt_interval")

    c3, c4, c5 = st.columns(3)
    with c3:
        opt_target = st.selectbox(
            "Ticker target",
            ["all tickers"] + VALID_CATEGORIES + tickers,
            key="opt_target",
            help="'all tickers' uses every ticker in the watchlist",
        )
    with c4:
        opt_iterations = st.number_input("Iterations", min_value=1, max_value=20, value=3, step=1)
    with c5:
        opt_model = st.selectbox("Model", _llm_models())

    c6, c7 = st.columns(2)
    with c6:
        opt_per_ticker = st.checkbox(
            "Per-ticker (save separate YAML per ticker)",
            value=False,
            help="Without this, one global optimized file is saved per strategy",
        )
    with c7:
        opt_leaps = st.checkbox(
            "LEAP mode (score by avg trade %)",
            value=False,
            help="Optimizes for options — biases toward fewer, higher-conviction signals",
        )

    if opt_leaps:
        opt_option_type = st.radio(
            "Option type", ["auto", "call", "put"], horizontal=True,
        )
    else:
        opt_option_type = "auto"

    if st.button("Run Optimizer", type="primary", key="run_optimize"):
        if not opt_strats:
            st.warning("Select at least one strategy.")
        else:
            cmd = [
                STONKS_BIN, "optimize",
                "--interval", opt_interval,
                "--iterations", str(opt_iterations),
                "--model", opt_model,
            ]

            if set(opt_strats) == set(strategy_names):
                cmd.append("--all-strategies")
            else:
                for name in opt_strats:
                    cmd += ["--strategy", strategy_map[name].name]

            if opt_target == "all tickers":
                cmd.append("--all-tickers")
            elif opt_target in VALID_CATEGORIES:
                # pass the category tickers via repeated --ticker flags
                cat_tickers = wl.get(opt_target, []) or []
                for t in cat_tickers:
                    cmd += ["--ticker", t]
                if not cat_tickers:
                    st.warning(f"No tickers in category '{opt_target}'.")
                    st.stop()
            else:
                cmd += ["--ticker", opt_target]

            if opt_per_ticker:
                cmd.append("--per-ticker")

            if opt_leaps:
                cmd += ["--leaps", "--option-type", opt_option_type]

            # total steps = strategies × tickers being optimized
            if opt_target == "all tickers":
                _opt_ticker_count = len(tickers)
            elif opt_target in VALID_CATEGORIES:
                _opt_ticker_count = len(wl.get(opt_target, []) or [])
            else:
                _opt_ticker_count = 1
            _opt_total = len(opt_strats) * _opt_ticker_count

            with st.status("Running optimizer...", expanded=True) as s:
                st.caption(f"`{' '.join(str(c) for c in cmd)}`")
                rc = _stream(cmd, s,
                             total=_opt_total,
                             step_marker="Optimized strategy saved")
                if rc == 0:
                    s.update(label="Optimization complete", state="complete", expanded=False)
                else:
                    s.update(label="Optimization failed — check output above", state="error")
