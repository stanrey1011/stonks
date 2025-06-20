import pandas as pd

df = pd.read_csv("project/data/ticker_data/AAPL.csv", parse_dates=["Date"])
print(f"Date range: {df['Date'].min().date()} → {df['Date'].max().date()}")
print(f"Total rows: {len(df)}")
