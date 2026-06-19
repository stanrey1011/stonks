"""List and cancel long-running stonks jobs in the *current* container.

The dashboard launches `optimize` / `pipeline` as subprocesses (dash/pages/7_Pipeline.py);
navigating away doesn't stop them, and repeated clicks stack up overlapping runs that all
contend for the local LLM. This module lets the GUI surface and cancel them.

Scope: it scans this process's own `/proc`, so it only sees jobs in this container. The
nightly scheduler runs in a separate container and is neither visible nor killable here.
Implemented with `/proc` + `os.kill` (no `procps`/`psutil` dependency).
"""

import os
import signal
import time

# keyword in the command line -> (friendly label, is it LLM-bound?)
JOB_KINDS = {
    "optimize":        ("Optimizer", True),
    "sentiment-score": ("Sentiment scoring", True),
    "news-backfill":   ("News backfill", False),
    "pipeline":        ("Data pipeline", False),
}

_CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100


def _cmdline(pid) -> str:
    with open(f"/proc/{pid}/cmdline", "rb") as f:
        return f.read().replace(b"\x00", b" ").decode("utf-8", "replace").strip()


def _btime():
    try:
        with open("/proc/stat") as f:
            for line in f:
                if line.startswith("btime"):
                    return int(line.split()[1])
    except Exception:
        pass
    return None


def _elapsed(pid):
    """Seconds since the process started, or None."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            after_comm = f.read().rsplit(")", 1)[1].split()  # skip pid + (comm)
        starttime = int(after_comm[19])  # field 22 of stat
        bt = _btime()
        if bt is None:
            return None
        return max(0, int(time.time() - (bt + starttime / _CLK_TCK)))
    except Exception:
        return None


def format_elapsed(secs) -> str:
    if secs is None:
        return "?"
    m, s = divmod(int(secs), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h else f"{m}m {s}s"


def _job_kind(cmd: str):
    """Return (label, is_llm) if cmd is a stonks long-job invocation, else None.
    Matches the `stonks <subcommand>` adjacency so a stray word (or the project path,
    which ends in 'stonks') can't false-positive."""
    for kw, meta in JOB_KINDS.items():
        if f"stonks {kw}" in cmd:
            return meta
    return None


def _is_stonks_job(cmd: str) -> bool:
    return _job_kind(cmd) is not None


def list_jobs() -> list[dict]:
    """Running stonks jobs in this container, oldest pid first."""
    self_pid = os.getpid()
    jobs = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        ipid = int(pid)
        if ipid == self_pid:
            continue
        try:
            cmd = _cmdline(pid)
        except Exception:
            continue
        meta = _job_kind(cmd) if cmd else None
        if meta is None:
            continue
        kind, is_llm = meta
        jobs.append({"pid": ipid, "cmd": cmd, "kind": kind,
                     "llm": is_llm, "elapsed": _elapsed(pid)})
    return sorted(jobs, key=lambda j: j["pid"])


def kill_job(pid: int, escalate: bool = True) -> bool:
    """Terminate a stonks job by pid. Re-verifies the pid is still a stonks job first
    (so a recycled pid can't be killed by mistake). SIGTERM, then SIGKILL if it lingers."""
    try:
        if not _is_stonks_job(_cmdline(pid)):
            return False
    except Exception:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except Exception:
        return False
    if escalate:
        time.sleep(2)
        try:
            if _is_stonks_job(_cmdline(pid)):
                os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
    return True


def cancel_all(llm_only: bool = False) -> int:
    """Cancel all running stonks jobs (or just the LLM-bound ones). Returns count signalled."""
    n = 0
    for j in list_jobs():
        if llm_only and not j["llm"]:
            continue
        if kill_job(j["pid"]):
            n += 1
    return n
