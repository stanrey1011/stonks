# stonkslib/cli/wipe_signals.py or inline in stonks.py
import shutil
import os

def wipe_signals(args):
    base = os.path.abspath(os.path.dirname(__file__))
    project_root = os.path.abspath(os.path.join(base, "../../"))

    target_map = {
        "signals": os.path.join(project_root, "data", "analysis", "signals"),
        "merged": os.path.join(project_root, "data", "analysis", "merged"),
        "raw": os.path.join(project_root, "data", "ticker_data", "raw"),
        "clean": os.path.join(project_root, "data", "ticker_data", "clean"),
    }

    if args.target == "all":
        for path in target_map.values():
            _safe_wipe(path)
    else:
        path = target_map[args.target]
        _safe_wipe(path)

def _safe_wipe(path):
    if os.path.exists(path):
        print(f"[⚠] Wiping {path}")
        shutil.rmtree(path)
        os.makedirs(path)
        print(f"[✓] Cleaned: {path}")
    else:
        print(f"[!] Path not found: {path}")
