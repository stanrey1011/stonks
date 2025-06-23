# stonkslib/fetch/guard.py

from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import warnings

def needs_update(file_path: Path, interval: str) -> bool:
    """Return True if the file is missing or outdated."""
    if not file_path.exists():
        return True

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            df = pd.read_csv(file_path, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, errors='coerce', utc=True)

        if df.empty:
            return True

        last_time = df.index[-1]

        now = datetime.utcnow().replace(tzinfo=last_time.tzinfo)

        delta = {
            "1m": timedelta(minutes=1),
            "2m": timedelta(minutes=2),
            "5m": timedelta(minutes=5),
            "15m": timedelta(minutes=15),
            "30m": timedelta(minutes=30),
            "1h": timedelta(hours=1),
            "1d": timedelta(days=1),
            "1wk": timedelta(weeks=1),
            "1mo": timedelta(days=30),  # Approximation
        }.get(interval, timedelta(days=1))  # Fallback to 1 day

        return now - last_time >= delta

    except Exception as e:
        print(f"[!] needs_update failed for {file_path.name}: {e}")
        return True
