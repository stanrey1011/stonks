import pandas as pd
from pathlib import Path
from stonkslib.utils.logging import setup_logging

PROJECT_ROOT = Path(__file__).resolve().parents[3]
logger = setup_logging(PROJECT_ROOT / "log", "analyze.log")

def analyze_covered_calls(ticker: str, strategy: str):
    """Analyze sell-side covered calls using cleaned data."""
    data_dir = Path(f"data/options_data/clean/sell/covered_calls/calls/{ticker}.csv")
    if not data_dir.exists():
        logger.warning(f"[!] No cleaned data found for {ticker} (covered_calls)")
        return None
    try:
        df = pd.read_csv(data_dir, parse_dates=['expiration'])
        df = df[(df['open_interest'] > 100) & 
                (df['expiration'] >= pd.Timestamp.now(tz='UTC') + pd.Timedelta(days=7)) &
                (df['expiration'] <= pd.Timestamp.now(tz='UTC') + pd.Timedelta(days=45))]
        df['signal'] = (df['bid'] > df['strike'] * 0.01).astype(int)
        df = df[['strike', 'expiration', 'bid', 'ask', 'open_interest', 'signal']]
        output_dir = Path(f"data/analysis/options/covered_calls/{ticker}")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "covered_calls_signals.csv"
        df.to_csv(output_path, index=False)
        logger.info(f"[✓] Saved covered calls signals for {ticker} → {output_path} ({len(df)} rows)")
        return df
    except Exception as e:
        logger.error(f"[!] Failed to analyze covered calls for {ticker}: {e}")
        return None