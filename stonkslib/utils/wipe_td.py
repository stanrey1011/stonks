from pathlib import Path

def clear_ticker_data():
    """
    Deletes all files inside each interval subdirectory of ticker_data,
    preserving folder structure.
    """
    # Go up two levels from this script to reach project root
    project_root = Path(__file__).resolve().parents[2]
    base_dir = project_root / "data" / "ticker_data"

    if not base_dir.exists():
        print(f"[!] Directory not found: {base_dir}")
        return

    deleted_files = 0
    for path in base_dir.rglob("*"):
        if path.is_file():
            try:
                path.unlink()
                print(f"[✓] Deleted: {path}")
                deleted_files += 1
            except Exception as e:
                print(f"[!] Failed to delete {path}: {e}")

    if deleted_files == 0:
        print("[i] No files found to delete.")
    else:
        print(f"[✓] Done. Deleted {deleted_files} file(s).")

if __name__ == "__main__":
    clear_ticker_data()
