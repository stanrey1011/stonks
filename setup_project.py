import os

FOLDER_STRUCTURE = [
    "project/data_collection",  # for fetch_data.py, clean_data.py, etc.
    "project/indicators",
    "project/patterns",
    "project/alerts",
    "project/trading_logic",
    "project/llm_integration",
    "project/execution",
    "project/data/ticker_data",  # clean separation: only data
    "project/data/charts/head_shoulders",
    "project/data/charts/cup_handle",
    "project/data/charts/triangles",
]

def create_directories(base_path="."):
    for folder in FOLDER_STRUCTURE:
        full_path = os.path.join(base_path, folder)
        os.makedirs(full_path, exist_ok=True)
        print(f"Created: {full_path}")

if __name__ == "__main__":
    create_directories()
