import os
import yfinance as yf
import yaml

DATA_DIR = "data/ticker_data"  # The root directory for saving data

def load_tickers(yaml_file="tickers.yaml"):
    with open(yaml_file, "r") as f:
        return yaml.safe_load(f)

def fetch_category(category: str, period: str = "1y", interval: str = "1d"):
    # Load tickers for the given category
    tickers_data = load_tickers()
    tickers = tickers_data.get(category)

    if not tickers:
        raise ValueError(f"Category '{category}' not found in tickers.yaml")

    # Correct the output path to save data into ticker_data/<interval>
    out_dir = os.path.join("data", "ticker_data", interval)
    os.makedirs(out_dir, exist_ok=True)

    for ticker in tickers:
        print(f"[↑] Fetching {ticker} for period '{period}' at interval '{interval}'...")
        try:
            # Fetch data with the given interval
            df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
            if not df.empty:
                # Save the data as <ticker>.csv without using category in the filename
                df.to_csv(os.path.join(output_dir, f"{ticker}.csv"))
                print(f"[✓] Saved: {ticker}")
            else:
                print(f"[!] No data for {ticker}")
        except Exception as e:
            print(f"[!] Error fetching {ticker}: {e}")
