import os
import yfinance as yf
import yaml

# Custom intervals and periods per category
CATEGORY_INTERVALS = {
    "stocks": [
        ("1m", "7d"),
        ("2m", "60d"),
        ("5m", "60d"),
        ("15m", "60d"),
        ("1h", "730d"),     # 2 years
        ("1d", "3y"),       # 3 years
        ("1wk", "4y"),      # 4 years
        ("1mo", "5y"),      # 5 years
    ],
    "etfs": [
        ("1m", "7d"),
        ("2m", "60d"),
        ("5m", "60d"),
        ("15m", "60d"),
        ("1h", "730d"),     # 2 years
        ("1d", "3y"),       # 3 years
        ("1wk", "4y"),      # 4 years
        ("1mo", "5y"),      # 5 years
    ],
    "crypto": [
        ("1m", "7d"),
        ("5m", "60d"),
        ("15m", "60d"),
        ("1d", "730d"),     # 2 years
        ("1wk", "1095d"),   # 3 years
    ],
}

def fetch_all(yaml_file="tickers.yaml", data_dir="data"):
    with open(yaml_file, "r") as f:
        all_tickers = yaml.safe_load(f)

    for category, tickers in all_tickers.items():
        intervals = CATEGORY_INTERVALS.get(category, [("1d", "1y")])  # fallback

        for ticker in tickers:
            for interval, period in intervals:
                print(f"[↑] Fetching {ticker} ({interval}, {period})...")
                try:
                    df = yf.download(ticker, interval=interval, period=period, progress=False)
                    if not df.empty:
                        out_dir = os.path.join("data", "ticker_data", interval)
                        os.makedirs(out_dir, exist_ok=True)
                        out_path = os.path.join(out_dir, f"{ticker}.csv")
                        df.to_csv(out_path)
                        print(f"[✓] Saved {ticker} → {interval}")
                    else:
                        print(f"[!] No data for {ticker} ({interval})")
                except Exception as e:
                    print(f"[!] Error fetching {ticker} ({interval}): {e}")
