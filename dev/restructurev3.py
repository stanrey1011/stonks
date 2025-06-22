import os
import shutil

ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
OLD_PACKAGE = os.path.join(ROOT_DIR, "stonks")
NEW_PACKAGE = os.path.join(ROOT_DIR, "stonkslib")

# Create new package folder
os.makedirs(NEW_PACKAGE, exist_ok=True)

# Move files and folders into stonkslib/
for item in os.listdir(OLD_PACKAGE):
    src = os.path.join(OLD_PACKAGE, item)
    dst = os.path.join(NEW_PACKAGE, item)
    if os.path.exists(dst):
        print(f"[!] Skipping {item}, already exists in stonkslib/")
        continue
    shutil.move(src, dst)
    print(f"[+] Moved {item} → stonkslib/")

# Clean up empty stonks/ folder if it’s now empty
try:
    os.rmdir(OLD_PACKAGE)
    print(f"[✓] Removed empty folder: {OLD_PACKAGE}")
except OSError:
    print(f"[!] Could not remove {OLD_PACKAGE} (not empty or in use)")

print("\n[✅] Structure cleaned. Update your import paths to use `stonkslib.`")
