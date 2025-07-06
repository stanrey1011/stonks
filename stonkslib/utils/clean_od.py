import os
import logging
import pandas as pd

# Setup logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

def clean_option_data(df):
    """Clean individual options dataframe and assign strategy labels and IV rank."""
    # Parse dates with timezone awareness
    df['lastTradeDate'] = pd.to_datetime(df['lastTradeDate'], utc=True)
    df['expirationDate'] = pd.to_datetime(df['expirationDate'], utc=True)

    # Drop rows missing critical numeric data
    critical_cols = ['impliedVolatility', 'strike', 'lastPrice', 'bid', 'ask']
    df = df.dropna(subset=critical_cols)

    # Fill missing volume/openInterest with zero using .loc to avoid warnings
    df.loc[:, 'volume'] = df['volume'].fillna(0)
    df.loc[:, 'openInterest'] = df['openInterest'].fillna(0)

    # Convert relevant columns to numeric
    numeric_cols = ['impliedVolatility', 'volume', 'openInterest', 'strike', 'lastPrice', 'bid', 'ask']
    for col in numeric_cols:
        df.loc[:, col] = pd.to_numeric(df[col], errors='coerce')

    # Drop rows that have become invalid after coercion
    df = df.dropna(subset=critical_cols)

    # Mark LEAPs (expiration > 1 year from now)
    now = pd.Timestamp.now(tz='UTC')
    df.loc[:, 'is_LEAP'] = df['expirationDate'] > (now + pd.DateOffset(years=1))

    # Default strategy label
    df.loc[:, 'strategy'] = 'regular'

    # Label LEAP strategy
    df.loc[df['is_LEAP'], 'strategy'] = 'LEAP'

    # Placeholder logic to mark spreads and condors (replace or expand as needed)
    df.loc[df['strategy'] == 'regular', 'strategy'] = 'spread'  # example
    df.loc[df['strategy'] == 'regular', 'strategy'] = 'condor'  # example

    # Calculate IV rank as a percentage
    if 'impliedVolatility' in df.columns and len(df) > 1:
        iv_min = df['impliedVolatility'].min()
        iv_max = df['impliedVolatility'].max()
        df.loc[:, 'iv_rank'] = (df['impliedVolatility'] - iv_min) / (iv_max - iv_min + 1e-6) * 100

    return df

def clean_options_data(raw_dir, clean_dir):
    """Clean all CSV files in raw_dir and save cleaned data in clean_dir."""
    if not os.path.exists(clean_dir):
        os.makedirs(clean_dir)
        logger.info(f"Created clean directory: {clean_dir}")

    found_files = False
    for filename in os.listdir(raw_dir):
        if not filename.lower().endswith('.csv'):
            continue
        found_files = True
        ticker = filename.split('.')[0]
        raw_file_path = os.path.join(raw_dir, filename)
        logger.info(f"Cleaning {raw_file_path}...")
        try:
            df = pd.read_csv(raw_file_path)
            if df.empty:
                logger.warning(f"Empty file: {raw_file_path}")
                continue

            df = clean_option_data(df)
            if df.empty:
                logger.warning(f"No valid data after cleaning: {raw_file_path}")
                continue

            save_cleaned_data(df, ticker, raw_dir, clean_dir)

        except Exception as e:
            logger.error(f"Failed to process {raw_file_path}: {e}")

    if not found_files:
        logger.error(f"No CSV files found in {raw_dir}")

def save_cleaned_data(df, ticker, raw_dir, clean_dir):
    """Save cleaned options data grouped by expiration date, preserving folder structure."""
    # Calculate relative path from raw base to replicate structure in clean_dir
    rel_path = os.path.relpath(raw_dir, start=os.path.commonpath([raw_dir, clean_dir]))
    base_clean_dir = os.path.join(clean_dir, rel_path)

    for expiry_date, group in df.groupby('expirationDate'):
        try:
            expiry_str = pd.Timestamp(expiry_date).strftime('%Y-%m-%d')
        except Exception as e:
            logger.error(f"Could not parse expiry date {expiry_date}: {e}")
            continue

        cleaned_dir = os.path.join(base_clean_dir, expiry_str)
        if not os.path.exists(cleaned_dir):
            os.makedirs(cleaned_dir)
            logger.info(f"Created directory: {cleaned_dir}")

        cleaned_file = os.path.join(cleaned_dir, f"{ticker}_{expiry_str}_clean.csv")

        if os.path.exists(cleaned_file):
            existing_df = pd.read_csv(cleaned_file)
            combined = pd.concat([existing_df, group], ignore_index=True)
            combined.drop_duplicates(subset=["contractSymbol"], keep="last", inplace=True)
            combined.to_csv(cleaned_file, index=False)
            logger.info(f"Updated cleaned data: {cleaned_file} ({len(group)} new rows, {len(combined)} total)")
        else:
            group.to_csv(cleaned_file, index=False)
            logger.info(f"Saved cleaned data: {cleaned_file} ({len(group)} rows)")

if __name__ == "__main__":
    RAW_DIR = 'data/options_data/raw/calls/buy/leaps'
    CLEAN_DIR = 'data/options_data/clean'
    logger.info("Starting options data cleaning process...")
    clean_options_data(RAW_DIR, CLEAN_DIR)
    logger.info("Options data cleaning completed.")
