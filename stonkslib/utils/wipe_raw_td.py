# stonkslib/utils/wipe_raw_td.py
from pathlib import Path

def clear_raw_td():
    """
    Deletes all files inside the raw ticker_data directory,
    preserving folder structure and skipping the clean directory.
    """
    # Go up two levels from this script to reach project root
    project_root = Path(__file__).resolve().parents[2]
    raw_dir = project_root / "data" / "ticker_data" / "raw"

    if not raw_dir.exists():
        print(f"[!] Raw directory not found: {raw_dir}")
        return

    deleted_files = 0
    for path in raw_dir.rglob("*"):
        if path.is_file():
            try:
                path.unlink()
                print(f"[✓] Deleted: {path}")
                deleted_files += 1
            except Exception as e:
                print(f"[!] Failed to delete {path}: {e}")

    if deleted_files == 0:
        print("[i] No files found to delete in raw.")
    else:
        print(f"[✓] Done. Deleted {deleted_files} raw file(s).")

if __name__ == "__main__":
    clear_raw_td()
