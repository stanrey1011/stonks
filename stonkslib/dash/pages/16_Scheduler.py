import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import yaml
import streamlit as st

from stonkslib.dash.common import load_watchlist, flat_tickers, STRATEGY_DIR
from stonkslib.llm import client
from stonkslib.utils import jobs as _jobs
from stonkslib.utils import scheduler as sch

st.set_page_config(page_title="Scheduler — Stonks", layout="wide")
st.title("🗓️ Optimize Scheduler")
st.caption("Launch optimizations as detached background jobs (they survive navigating away) "
           "and define recurring schedules. Schedules are stored in data/optimize_schedules.json "
           "and run by the scheduler container every minute (UTC). Per-ticker runs over a large "
           "watchlist take hours — schedule them off-hours.")

wl = load_watchlist()
tickers = flat_tickers(wl)
strategy_files = sorted(STRATEGY_DIR.glob("*.yaml"))
strategy_names = [yaml.safe_load(p.read_text()).get("name", p.stem) for p in strategy_files]
strategy_map = dict(zip(strategy_names, strategy_files))


def _llm_models() -> list[str]:
    return client.list_models() or [client.default_model()]


# ── running jobs panel ──────────────────────────────────────────────────────────
_running = _jobs.list_jobs()
_n_llm = sum(1 for j in _running if j["llm"])
with st.expander(f"🧹 Running jobs — {len(_running)} active" if _running else "🧹 Running jobs",
                 expanded=bool(_running)):
    cc1, cc2, _ = st.columns([1, 2, 5])
    if cc1.button("🔄 Refresh", key="sched_jobs_refresh"):
        st.rerun()
    if cc2.button(f"🛑 Cancel all LLM jobs ({_n_llm})", key="sched_jobs_cancel_llm",
                  disabled=_n_llm == 0):
        st.success(f"Cancelled {_jobs.cancel_all(llm_only=True)} LLM job(s).")
        st.rerun()
    if not _running:
        st.info("No stonks jobs running in this container.")
    for j in _running:
        jc1, jc2 = st.columns([8, 1])
        tag = "🧠 " if j["llm"] else ""
        jc1.markdown(f"{tag}**{j['kind']}** · PID {j['pid']} · running "
                     f"{_jobs.format_elapsed(j['elapsed'])}  \n`{j['cmd'][:140]}`")
        if jc2.button("✖ Cancel", key=f"sched_cancel_{j['pid']}"):
            ok = _jobs.kill_job(j["pid"])
            st.success(f"Cancelled PID {j['pid']}." if ok else f"Could not cancel PID {j['pid']}.")
            st.rerun()


# ── shared config block ─────────────────────────────────────────────────────────
def _config_block(prefix: str) -> dict:
    c1, c2 = st.columns(2)
    with c1:
        strats = st.multiselect("Strategies", strategy_names, default=strategy_names,
                                key=f"{prefix}_strats")
    with c2:
        interval = st.selectbox("Interval", ["1d", "1wk", "1h"], key=f"{prefix}_interval")
    c3, c4, c5 = st.columns(3)
    with c3:
        target = st.selectbox("Ticker target", ["all tickers"] + tickers, key=f"{prefix}_target",
                              help="Per-ticker tuning runs once per ticker — see the estimate.")
    with c4:
        iterations = st.number_input("Iterations", 1, 20, 3, 1, key=f"{prefix}_iter")
    with c5:
        model = st.selectbox("Model", _llm_models(), key=f"{prefix}_model")
    c6, c7 = st.columns(2)
    with c6:
        per_ticker = st.checkbox("Per-ticker YAMLs", value=False, key=f"{prefix}_pt",
                                 help="Without this, one global optimized file per strategy")
    with c7:
        leaps = st.checkbox("LEAP mode (score by avg trade %)", value=False, key=f"{prefix}_leaps")
    option_type = (st.radio("Option type", ["auto", "call", "put"], horizontal=True,
                            key=f"{prefix}_ot") if leaps else "auto")

    n_strat = len(strats)
    n_tick = len(tickers) if target == "all tickers" else 1
    llm_calls = max(iterations - 1, 0) * n_strat * (n_tick if per_ticker else 1)
    if not strats:
        st.warning("Select at least one strategy.")
    else:
        warn = " ⚠️ that's a lot — schedule off-hours" if llm_calls > 200 else ""
        st.caption(f"≈ **{llm_calls} LLM call(s)** per run "
                   f"({n_strat} strat × {n_tick if per_ticker else 1} target × {max(iterations-1,0)} iter)"
                   f"{warn}")
    return {"strats": strats, "interval": interval, "target": target, "iterations": iterations,
            "model": model, "per_ticker": per_ticker, "leaps": leaps, "option_type": option_type}


def _args_from_cfg(cfg: dict) -> list[str]:
    all_sel = set(cfg["strats"]) == set(strategy_names)
    files = [strategy_map[n].name for n in cfg["strats"]]
    return sch.build_optimize_args(
        files, all_strategies=all_sel,
        target="all" if cfg["target"] == "all tickers" else cfg["target"],
        model=cfg["model"], interval=cfg["interval"], iterations=int(cfg["iterations"]),
        per_ticker=cfg["per_ticker"], leaps=cfg["leaps"], option_type=cfg["option_type"])


tab_run, tab_sched, tab_logs = st.tabs(["▶ Run now", "🗓️ Schedules", "📜 Logs"])

# ── Run now (detached) ──────────────────────────────────────────────────────────
with tab_run:
    st.subheader("Run an optimization now (background)")
    cfg = _config_block("run")
    label = st.text_input("Job label (for the log filename)", value="optimize", key="run_label")
    if st.button("▶ Run now (background)", type="primary", key="run_now_btn",
                 disabled=not cfg["strats"]):
        args = _args_from_cfg(cfg)
        info = sch.run_detached(args, label=label)
        st.success(f"Launched PID {info['pid']} — logging to `{info['log']}`")
        st.code("stonks " + " ".join(args), language="bash")
        st.caption("Track/cancel it in **Running jobs** above, or watch it in the **Logs** tab.")

# ── Schedules (JSON store) ──────────────────────────────────────────────────────
with tab_sched:
    st.subheader("Create a recurring schedule (UTC)")
    cfg = _config_block("sch")
    s1, s2, s3 = st.columns([2, 3, 1])
    with s1:
        name = st.text_input("Schedule name", placeholder="e.g. leaps-nightly", key="sch_name")
    with s2:
        day_labels = st.multiselect("Days", [n for _, n in sch.WEEKDAYS],
                                    default=["Mon", "Tue", "Wed", "Thu", "Fri"], key="sch_days")
    with s3:
        at = st.time_input("At (UTC)", key="sch_time")
    days = [iso for iso, n in sch.WEEKDAYS if n in day_labels]

    can_create = bool(cfg["strats"] and name.strip() and days)
    if st.button("➕ Create / update schedule", type="primary", key="sch_create",
                 disabled=not can_create):
        sch.create_schedule(name, days, at.hour, at.minute, _args_from_cfg(cfg))
        st.success(f"Saved schedule `{sch._slug(name)}`.")
        st.rerun()
    if not (cfg["strats"] and days):
        st.caption("Pick at least one strategy and one day.")

    st.divider()
    st.subheader("Existing schedules")
    schedules = sch.list_schedules()
    if not schedules:
        st.info("No schedules yet — create one above.")
    for s in schedules:
        nr = sch.next_run(s)
        dnames = ",".join(n for iso, n in sch.WEEKDAYS if iso in s.get("days", []))
        on = s.get("enabled", True)
        h1, h2, h3, h4 = st.columns([5, 2, 1, 1])
        h1.markdown(
            f"{'🟢' if on else '⚪'} **{s['id']}** · {dnames} at "
            f"{s['hour']:02d}:{s['minute']:02d} UTC  \n"
            f"<small>next: {nr.strftime('%Y-%m-%d %H:%M UTC') if nr else '—'}</small>  \n"
            f"`stonks {' '.join(s['args'])}`", unsafe_allow_html=True)
        if h2.button("▶ Run now", key=f"sch_runnow_{s['id']}"):
            info = sch.run_detached(s["args"], label=s["id"])
            st.success(f"Launched PID {info['pid']}.")
        if h3.button("⏸ Off" if on else "▶ On", key=f"sch_toggle_{s['id']}"):
            sch.set_enabled(s["id"], not on)
            st.rerun()
        if h4.button("🗑", key=f"sch_del_{s['id']}"):
            sch.delete_schedule(s["id"])
            st.rerun()
    if schedules:
        st.caption("Schedules fire only when the **stonks-scheduler** container is running "
                   "(prod has `COMPOSE_PROFILES=scheduler`; a dashboard-only dev box won't fire them).")

# ── Logs ────────────────────────────────────────────────────────────────────────
with tab_logs:
    st.subheader("Recent run logs")
    logs = sch.recent_logs()
    if not logs:
        st.info("No background-run logs yet. Launch one from **Run now**.")
    else:
        pick = st.selectbox("Log file", logs, format_func=lambda p: p.name, key="log_pick")
        if st.columns([1, 7])[0].button("🔄 Refresh", key="log_refresh"):
            st.rerun()
        st.code(sch.tail(pick, n=300), language="text")
