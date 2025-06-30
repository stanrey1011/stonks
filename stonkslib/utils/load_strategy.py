import yaml
from pathlib import Path

def load_strategy_config(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Strategy config {path} does not exist")
    with open(path, "r") as f:
        return yaml.safe_load(f)
