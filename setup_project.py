import os

# Define folder structure
FOLDER_STRUCTURE = [
    "project/data_collection",
    "project/indicators",
    "project/patterns",
    "project/alerts",
    "project/trading_logic",
    "project/llm_integration",
    "project/execution",
    "project/data/ticker_data",
    "project/data/charts/head_shoulders",
    "project/data/charts/cup_handle",
    "project/data/charts/triangles",
]

# Folders that should be Python packages
PACKAGE_FOLDERS = [
    "project",
    "project/data_collection",
    "project/indicators",
    "project/patterns",
    "project/alerts",
    "project/trading_logic",
    "project/llm_integration",
    "project/execution",
]

def create_directories(base_path="."):
    for folder in FOLDER_STRUCTURE:
        full_path = os.path.join(base_path, folder)
        os.makedirs(full_path, exist_ok=True)
        print(f"Created: {full_path}")

def create_init_files(base_path="."):
    for package in PACKAGE_FOLDERS:
        init_path = os.path.join(base_path, package, "__init__.py")
        if not os.path.exists(init_path):
            with open(init_path, "w") as f:
                f.write("# Auto-generated package initializer\n")
            print(f"Created: {init_path}")

if __name__ == "__main__":
    create_directories()
    create_init_files()
