# stonkslib/dash/data.py

import pandas as pd
import yaml
from pathlib import Path

def load_tickers(yaml_path):
    with open(yaml_path, "r") as f:
        tickers = yaml.safe_load(f)
    all_tickers = []
    for cat, tlist in tickers.items():
        all_tickers.extend(tlist)
    return tickers, all_tickers

def get_asset_type(ticker, tickers_dict):
    for cat, tlist in tickers_dict.items():
        if ticker in tlist:
            return cat
    return "unknown"

def load_and_filter_df(DATA_PATH, interval, asset_type):
    df = pd.read_csv(DATA_PATH, parse_dates=True, index_col=0)
    # Timezone logic
    if interval in ["1m","2m","5m","15m","30m","1h"]:
        if getattr(df.index, "tz", None) is None:
            df.index = pd.to_datetime(df.index, utc=True).tz_convert('US/Eastern')
        else:
            df.index = df.index.tz_convert('US/Eastern')
    else:
        if getattr(df.index, "tz", None) is None:
            df.index = pd.to_datetime(df.index, utc=True)
        else:
            df.index = df.index.tz_convert('UTC')
    # Market hours filter for stocks/etfs intraday
    if asset_type in ['stocks', 'etfs'] and interval in ["1m","2m","5m","15m","30m","1h"]:
        market_open = 9*60 + 30
        market_close = 16*60
        minutes_of_day = df.index.hour * 60 + df.index.minute
        in_market_hours = (
            (minutes_of_day >= market_open) &
            (minutes_of_day < market_close) &
            (df.index.dayofweek < 5)
        )
        df = df[in_market_hours]
        df = df.dropna(subset=["Open", "High", "Low", "Close"], how="any")
        # df = df[df["Volume"] > 0]
    return df
