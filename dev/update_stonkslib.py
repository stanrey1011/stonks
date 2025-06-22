import os
import shutil
import zipfile
import tempfile

# === Configuration ===
ZIP_PATH = "stonks_clean_fixed.zip"
TARGET_DIR = os.path.join(os.getcwd(), "stonkslib")  # current working dir: ./stonkslib

# === Unzip to temp ===
with tempfile.TemporaryDirectory() as tmpdir:
    with zipfile.ZipFile(ZIP_PATH, 'r') as zip_ref:
        zip_ref.extractall(tmpdir)
        print(f"[+] Extracted to: {tmpdir}")

    # Adjusted for zip structure: stonks/stonkslib/
    new_lib_path = os.path.join(tmpdir, "stonks", "stonkslib")

    if not os.path.isdir(new_lib_path):
        raise FileNotFoundError("❌ 'stonks/stonkslib/' not found inside ZIP.")

    # === Delete old stonkslib ===
    if os.path.exists(TARGET_DIR):
        print(f"[~] Removing old stonkslib at: {TARGET_DIR}")
        shutil.rmtree(TARGET_DIR)

    # === Copy updated one in place ===
    shutil.copytree(new_lib_path, TARGET_DIR)
    print(f"[✓] Updated 'stonkslib/' successfully.")
