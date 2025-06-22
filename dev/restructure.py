import os
import shutil

# Define base and target directories
base = os.path.abspath(os.path.dirname(__file__))
src = base
target = os.path.join(base, "stonks")

# Directories to move into `stonks/`
move_items = [
    "project/alerts",
    "project/execution",
    "project/indicators",
    "project/llm_integration",
    "project/patterns",
    "project/trading_logic",
    "project/utils.py",
    "project/stonks.py",
    "project/stonks_cli.py",
    "project/fetch_data.py",
    "project/check_data_span.py",
    "tickers.yaml",
]

# Ensure the new structure exists
os.makedirs(target, exist_ok=True)
os.makedirs(os.path.join(target, "data"), exist_ok=True)

# Move items
for item in move_items:
    src_path = os.path.join(base, item)
    dst_path = os.path.join(target, os.path.basename(item))
    try:
        shutil.move(src_path, dst_path)
        print(f"Moved: {src_path} → {dst_path}")
    except FileNotFoundError:
        print(f"[!] Not found: {src_path}")
    except Exception as e:
        print(f"[!] Error moving {src_path}: {e}")

# Optional cleanup: remove the now-empty 'project' directory if it only had those files
try:
    if os.path.isdir(os.path.join(base, "project")) and not os.listdir(os.path.join(base, "project")):
        os.rmdir(os.path.join(base, "project"))
        print("Removed empty 'project/' directory.")
except Exception as e:
    print(f"[!] Could not remove project/: {e}")
