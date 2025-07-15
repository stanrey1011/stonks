import pandas as pd
from pathlib import Path
from stonkslib.utils.logging import setup_logging

PROJECT_ROOT = Path(__file__).resolve().parents[3]
logger = setup_logging(PROJECT_ROOT / "log", "analyze.log")

def analyze_wheel(ticker: str, strategy: str):
    """Analyze wheel strategy (sell calls and puts) using cleaned data."""
    data_dir_calls = Path(f"data/options_data/clean/sell/covered_calls/calls/{ticker}.csv")
    data_dir_puts = Path(f"data/options_data/clean/sell/secured_puts/puts/{ticker}.csv")
    if not (data_dir_calls.exists() or data_dir_puts.exists()):
        logger.warning(f"[!] No cleaned data found for {ticker} (wheel)")
        return None
    try:
        df_calls = pd.read_csv(data_dir_calls, parse_dates=['expiration']) if data_dir_calls.exists() else pd.DataFrame()
        df_puts = pd.read_csv(data_dir_puts, parse_dates=['expiration']) if data_dir_puts.exists() else pd.DataFrame()
        df = pd.concat([df_calls, df_puts])
        df = df[(df['open_interest'] > 150) & 
                (df['expiration'] <= pd.Timestamp.now(tz='UTC') + pd.Timedelta(days=45))]
        df['signal'] = (df['bid'] > 0.5).astype(int)
        df = df[['strike', 'expiration', 'bid', 'ask', 'open_interest', 'signal']]
        output_dir = Path(f"data/analysis/options/wheel/{ticker}")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "wheel_signals.csv"
        df.to_csv(output_path, index=False)
        logger.info(f"[✓] Saved wheel signals for {ticker} → {output_path} ({len(df)} rows)")
        return df
    except Exception as e:
        logger.error(f"[!] Failed to analyze wheel for {ticker}: {e}")
        return None