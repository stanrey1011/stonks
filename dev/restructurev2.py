import os
import shutil

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def safe_move(src, dst):
    if os.path.exists(src):
        print(f"[→] Moving {src} → {dst}")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)

def safe_delete(path):
    if os.path.exists(path):
        print(f"[✂] Deleting {path}")
        shutil.rmtree(path)

def main():
    # Cleanup legacy folders
    safe_delete(os.path.join(PROJECT_ROOT, "project"))
    safe_delete(os.path.join(PROJECT_ROOT, "stonkslib"))
    safe_delete(os.path.join(PROJECT_ROOT, "stonks.egg-info"))
    safe_delete(os.path.join(PROJECT_ROOT, "__pycache__"))

    # Move top-level files into stonks package
    top_files = ["fetch_data.py", "check_data_span.py", "tickers.yaml"]
    for filename in top_files:
        src = os.path.join(PROJECT_ROOT, filename)
        dst = os.path.join(PROJECT_ROOT, "stonks", filename)
        safe_move(src, dst)

    # Move data folders into stonks/data/
    for subfolder in ["charts", "ticker_data"]:
        src = os.path.join(PROJECT_ROOT, "data", subfolder)
        dst = os.path.join(PROJECT_ROOT, "stonks", "data", subfolder)
        safe_move(src, dst)

    # Remove empty top-level data/ folder
    safe_delete(os.path.join(PROJECT_ROOT, "data"))

    print("\n[✓] Restructure complete!")

if __name__ == "__main__":
    main()
