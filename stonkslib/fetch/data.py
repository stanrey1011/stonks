# stonkslib/fetch/data.py

from pathlib import Path
import yfinance as yf
import yaml
import logging
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)


from stonkslib.fetch.ranges import fetch_all  # Optional: if you want to call fetch_all from here

# Set up logging
LOG_DIR = Path(__file__).resolve().parents[2] / "log"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "fetch.log"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Data directory
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "ticker_data"

def load_tickers(yaml_file="tickers.yaml"):
    base_dir = Path(__file__).resolve().parents[2]
    yaml_path = base_dir / yaml_file
    with open(yaml_path, "r") as f:
        return yaml.safe_load(f)

def fetch_category(category: str, period: str = "1y", interval: str = "1d"):
    tickers_data = load_tickers()
    tickers = tickers_data.get(category)

    if not tickers:
        raise ValueError(f"Category '{category}' not found in tickers.yaml")

    out_dir = DATA_DIR / interval
    out_dir.mkdir(parents=True, exist_ok=True)

    for ticker in tickers:
        logging.info(f"Fetching {ticker} for period '{period}' at interval '{interval}'...")
        try:
            df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
            if not df.empty:
                out_file = out_dir / f"{ticker}.csv"
                df.to_csv(out_file, mode="a", header=True)  # append to file
                size_kb = out_file.stat().st_size / 1024
                logging.info(f"Saved {ticker} ({len(df)} rows, {size_kb:.2f} KB)")
            else:
                logging.warning(f"No data for {ticker}")
        except Exception as e:
            logging.error(f"Error fetching {ticker}: {e}")

# Enable to run directly
if __name__ == "__main__":
    # Run both specific category and full-range fetch
    fetch_category("stocks", period="1y", interval="1d")
    fetch_all()
