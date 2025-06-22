def load_ticker_data(ticker, category, interval, base_dir="data/ticker_data"):
    """
    Load data from: data/ticker_data/<interval>/<ticker>.csv
    """
    filename = f"{ticker}.csv"  # Just use the ticker name
    path = os.path.join(base_dir, interval, filename)

    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} does not exist.")

    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df
