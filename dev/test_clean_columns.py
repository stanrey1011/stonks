import pandas as pd
from pathlib import Path

def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    # Promote index into a column if necessary
    if df.index.name is not None:
        df.reset_index(inplace=True)

    # Coerce date parsing from the first column
    df[df.columns[0]] = pd.to_datetime(df[df.columns[0]], errors='coerce')

    # Drop rows with invalid dates
    df.dropna(subset=[df.columns[0]], inplace=True)

    # --- Early exit if DataFrame is empty now ---
    if df.empty:
        print("Warning: DataFrame is empty after removing invalid dates.")
        return df

    # Rename the date column to "Date" and set it as index
    df.rename(columns={df.columns[0]: "Date"}, inplace=True)
    df.set_index("Date", inplace=True)

    # Drop the first row if it contains column headers repeated as data
    if str(df.index[0]).lower() in ("ticker", "date"):
        df = df.iloc[1:]

    # Drop duplicate columns like ('Close', 'AAPL'), etc.
    df = df.loc[:, ~df.columns.astype(str).str.startswith("('")]

    # Strip MultiIndex or weird column levels if still present
    df.columns = [str(col).split("'")[-2] if "('" in str(col) else col for col in df.columns]

    return df

if __name__ == "__main__":
    path = Path("data/ticker_data/clean/1d/MSFT.csv")
    # Remove date_format, use parse_dates and index_col
    df = pd.read_csv(path, index_col=0, parse_dates=[0])

    df_cleaned = clean_columns(df)
    print(df_cleaned.head())
