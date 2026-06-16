"""Curated 'active' strategy set.

As the strategy library grows, fanning out over every YAML on each alert scan,
backtest sweep, optimize run, and dashboard render scales linearly and gets
expensive. The *active set* is a small curated list (config.yaml: `active_strategies`)
that those default fan-outs use instead. A full sweep is still available explicitly
(CLI `--every-strategy`).

The active set is the seam workstream D (the eval/curation loop) writes back into:
strategies get promoted in / retired out based on measured performance.
"""

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = PROJECT_ROOT / "stonkslib" / "strategies"
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

# Fallback if config.yaml has no `active_strategies:` key.
DEFAULT_ACTIVE = ["rsi_macd", "supertrend", "bollinger"]


def all_strategy_paths() -> list[Path]:
    """Every base strategy YAML (the full sweep)."""
    return sorted(STRATEGY_DIR.glob("*.yaml"))


def active_strategy_names() -> list[str]:
    """Configured active strategy stems, in config order."""
    try:
        cfg = yaml.safe_load(open(CONFIG_PATH)) or {}
        names = cfg.get("active_strategies")
        if names:
            return [Path(str(n)).stem for n in names]
    except Exception:
        pass
    return list(DEFAULT_ACTIVE)


def active_strategy_paths() -> list[Path]:
    """Curated subset of strategy YAMLs, in config order.

    Falls back to the full set if none of the configured names resolve to a file
    (so a typo never silently scans nothing).
    """
    names = active_strategy_names()
    order = {n: i for i, n in enumerate(names)}
    wanted = set(names)
    paths = [p for p in all_strategy_paths() if p.stem in wanted]
    if not paths:
        return all_strategy_paths()
    return sorted(paths, key=lambda p: order.get(p.stem, 10_000))


def resolve_strategy_set(every: bool = False) -> list[Path]:
    """Default fan-out target: active set, or the full set when `every` is True."""
    return all_strategy_paths() if every else active_strategy_paths()
