import pandas as pd
from pathlib import Path
from stonkslib.utils.logging import setup_logging

PROJECT_ROOT = Path(__file__).resolve().parents[3]
logger = setup_logging(PROJECT_ROOT / "log", "analyze.log")

def analyze_leaps_puts(ticker: str, strategy: str):
    """Analyze buy-side LEAPS puts using cleaned data."""
    data_dir = Path(f"data/options_data/clean/leaps/puts/{ticker}.csv")
    if not data_dir.exists():
        logger.warning(f"[!] No cleaned data found for {ticker} (leaps_puts)")
        return None
    try:
        df = pd.read_csv(data_dir, parse_dates=['expiration'])
        df = df[(df['open_interest'] > 100) & 
                (df['expiration'] > pd.Timestamp.now(tz='UTC') + pd.Timedelta(days=365))]
        df['signal'] = (df['bid'] > df['ask'] * 0.9).astype(int)
        df = df[['strike', 'expiration', 'bid', 'ask', 'open_interest', 'signal']]
        output_dir = Path(f"data/analysis/options/leaps_puts/{ticker}")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "leaps_puts_signals.csv"
        df.to_csv(output_path, index=False)
        logger.info(f"[✓] Saved LEAPS puts signals for {ticker} → {output_path} ({len(df)} rows)")
        return df
    except Exception as e:
        logger.error(f"[!] Failed to analyze LEAPS puts for {ticker}: {e}")
        return None