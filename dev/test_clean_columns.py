import pandas as pd
from pathlib import Path

def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    # Promote index into a column if necessary
    if df.index.name is not None:
        df.reset_index(inplace=True)

    # Coerce date parsing from the first column
    df[df.columns[0]] = pd.to_datetime(df[df.columns[0]], format="%Y-%m-%d", errors='coerce')

    # Drop rows with invalid dates
    df.dropna(subset=[df.columns[0]], inplace=True)

    # Rename the date column to "Date" and set it as index
    df.rename(columns={df.columns[0]: "Date"}, inplace=True)
    df.set_index("Date", inplace=True)

    # Drop the first row if it contains column headers repeated as data
    if df.index[0] == "Ticker" or df.index[0] == "Date":
        df = df.iloc[1:]

    # Drop duplicate columns like ('Close', 'AAPL'), etc.
    df = df.loc[:, ~df.columns.astype(str).str.startswith("('")]

    # Strip MultiIndex or weird column levels if still present
    df.columns = [str(col).split("'")[-2] if "('" in str(col) else col for col in df.columns]

    return df

if __name__ == "__main__":
    path = Path("data/ticker_data/clean/1d/MSFT.csv")
    df = pd.read_csv(path, index_col=0, parse_dates=[0], date_format="%Y-%m-%d")

    df_cleaned = clean_columns(df)
    print(df_cleaned.head())
