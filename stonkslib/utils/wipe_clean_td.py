# stonkslib/utils/wipe_clean_td.py
from pathlib import Path

def clear_clean_td():
    """
    Deletes all files inside the clean ticker_data directory,
    preserving folder structure and skipping the raw directory.
    """
    # Go up two levels from this script to reach project root
    project_root = Path(__file__).resolve().parents[2]
    clean_dir = project_root / "data" / "ticker_data" / "clean"

    if not clean_dir.exists():
        print(f"[!] Clean directory not found: {clean_dir}")
        return

    deleted_files = 0
    for path in clean_dir.rglob("*"):
        if path.is_file():
            try:
                path.unlink()
                print(f"[✓] Deleted: {path}")
                deleted_files += 1
            except Exception as e:
                print(f"[!] Failed to delete {path}: {e}")

    if deleted_files == 0:
        print("[i] No files found to delete in clean.")
    else:
        print(f"[✓] Done. Deleted {deleted_files} clean file(s).")

if __name__ == "__main__":
    clear_clean_td()
