import pandas as pd
import yfinance as yf
import yaml
from pathlib import Path
import warnings
import time
from datetime import datetime
from stonkslib.utils.logging import setup_logging
from stonkslib.fetch.guard import needs_update

# Suppress warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

# Load configuration
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"

# Setup logging
logger = setup_logging(PROJECT_ROOT / "log", "fetch.log")

# Load config.yaml
try:
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)
    if config is None:
        raise ValueError("config.yaml is empty or invalid")
except FileNotFoundError:
    logger.error(f"[!] Config file not found at {CONFIG_PATH}")
    config = {
        "project": {
            "ticker_yaml": "tickers.yaml",
            "options_data_dir": "data/options_data/raw",
            "log_dir": "log"
        },
        "strategies": {
            "leaps": {"output_dir": "calls/buy/leaps", "min_dte": 270, "max_dte": 9999, "option_type": "calls", "min_volume": 0, "min_open_interest": 0},
            "covered_calls": {"output_dir": "calls/sell/covered_calls", "min_dte": 0, "max_dte": 90, "option_type": "calls", "min_volume": 0, "min_open_interest": 0},
            "secured_puts": {"output_dir": "puts/sell/secured_puts", "min_dte": 0, "max_dte": 90, "option_type": "puts", "min_volume": 0, "min_open_interest": 0},
            "iron_condors": {"output_dir": "calls/sell/iron_condor", "min_dte": 0, "max_dte": 90, "option_type": "calls and puts", "strike_spread": 15.0, "min_volume": 0, "min_open_interest": 0},
            "straddles": {"output_dir": "calls/buy/straddle", "min_dte": 0, "max_dte": 90, "option_type": "calls and puts", "same_strike": True, "min_volume": 0, "min_open_interest": 0},
            "strangles": {"output_dir": "calls/buy/strangle", "min_dte": 0, "max_dte": 90, "option_type": "calls and puts", "strike_spread": 15.0, "min_volume": 0, "min_open_interest": 0},
            "credit_spreads": {"output_dir": "calls/sell/credit_spread", "min_dte": 0, "max_dte": 90, "option_type": "calls", "strike_spread": 10.0, "min_volume": 0, "min_open_interest": 0},
            "calendar_spreads": {"output_dir": "calls/buy/calendar_spread", "min_dte": 30, "max_dte": 365, "option_type": "calls", "multi_expirations": True, "min_volume": 0, "min_open_interest": 0}
        }
    }
except Exception as e:
    logger.error(f"[!] Error loading config.yaml: {e}")
    config = {
        "project": {
            "ticker_yaml": "tickers.yaml",
            "options_data_dir": "data/options_data/raw",
            "log_dir": "log"
        },
        "strategies": {
            "leaps": {"output_dir": "calls/buy/leaps", "min_dte": 270, "max_dte": 9999, "option_type": "calls", "min_volume": 0, "min_open_interest": 0},
            "covered_calls": {"output_dir": "calls/sell/covered_calls", "min_dte": 0, "max_dte": 90, "option_type": "calls", "min_volume": 0, "min_open_interest": 0},
            "secured_puts": {"output_dir": "puts/sell/secured_puts", "min_dte": 0, "max_dte": 90, "option_type": "puts", "min_volume": 0, "min_open_interest": 0},
            "iron_condors": {"output_dir": "calls/sell/iron_condor", "min_dte": 0, "max_dte": 90, "option_type": "calls and puts", "strike_spread": 15.0, "min_volume": 0, "min_open_interest": 0},
            "straddles": {"output_dir": "calls/buy/straddle", "min_dte": 0, "max_dte": 90, "option_type": "calls and puts", "same_strike": True, "min_volume": 0, "min_open_interest": 0},
            "strangles": {"output_dir": "calls/buy/strangle", "min_dte": 0, "max_dte": 90, "option_type": "calls and puts", "strike_spread": 15.0, "min_volume": 0, "min_open_interest": 0},
            "credit_spreads": {"output_dir": "calls/sell/credit_spread", "min_dte": 0, "max_dte": 90, "option_type": "calls", "strike_spread": 10.0, "min_volume": 0, "min_open_interest": 0},
            "calendar_spreads": {"output_dir": "calls/buy/calendar_spread", "min_dte": 30, "max_dte": 365, "option_type": "calls", "multi_expirations": True, "min_volume": 0, "min_open_interest": 0}
        }
    }

OPTIONS_RAW_DIR = PROJECT_ROOT / config["project"]["options_data_dir"]
LOG_DIR = PROJECT_ROOT / config["project"]["log_dir"]

# Re-setup logging
logger = setup_logging(LOG_DIR, "fetch.log")

def preprocess_options_data(df):
    """Standardize options data for LLM compatibility."""
    if df.empty:
        return df
    df["expirationDate"] = pd.to_datetime(df["expirationDate"]).dt.strftime("%Y-%m-%d")
    columns = ["expirationDate", "lastPrice", "strike", "daysToExpiration", "optionType", "bid", "ask", "volume", "openInterest", "impliedVolatility", "inTheMoney"]
    return df[[col for col in columns if col in df.columns]]

def fetch_option_chain(ticker, min_days_out, max_days_out, option_type, multi_expirations=False, same_strike=False, strike_spread=None, min_volume=0, min_open_interest=0):
    """Fetch options chain data with strategy-specific filtering."""
    try:
        ticker_obj = yf.Ticker(ticker)
        expirations = ticker_obj.options
        df_list = []
        now_utc = pd.Timestamp.now(tz='UTC')
        stock_price = ticker_obj.history(period="1d")["Close"].iloc[-1]
        logger.info(f"[i] Fetching options for {ticker}, stock price: {stock_price}")
        most_liquid_strike = None
        for exp in expirations:
            exp_date = pd.to_datetime(exp)
            if exp_date.tzinfo is None:
                exp_date = exp_date.tz_localize('UTC')
            else:
                exp_date = exp_date.tz_convert('UTC')
            dte = (exp_date - now_utc).days
            if min_days_out <= dte <= max_days_out:
                opt = ticker_obj.option_chain(exp)
                contracts = pd.concat([opt.calls, opt.puts], ignore_index=True) if option_type == "calls and puts" else (opt.calls if option_type == "calls" else opt.puts)
                if not contracts.empty:
                    # Log raw data for debugging
                    logger.debug(f"[d] Raw data for {ticker}, expiration {exp}: {len(contracts)} rows")
                    contracts["expirationDate"] = exp_date
                    contracts["ticker"] = ticker
                    contracts["daysToExpiration"] = dte
                    contracts["optionType"] = "calls" if option_type == "calls" else ("puts" if option_type == "puts" else option_type)
                    if same_strike and option_type == "calls and puts":
                        calls = opt.calls
                        puts = opt.puts
                        common_strikes = set(calls["strike"]).intersection(set(puts["strike"]))
                        if common_strikes:
                            atm_strike = min(common_strikes, key=lambda x: abs(x - stock_price))
                            contracts = pd.concat([
                                calls[calls["strike"] == atm_strike],
                                puts[puts["strike"] == atm_strike]
                            ], ignore_index=True)
                            contracts["optionType"] = contracts["contractSymbol"].str[-9:].str[0].map({'C': 'calls', 'P': 'puts'})
                        else:
                            # Fallback: Use nearest call and put strikes
                            call_strike = calls["strike"].iloc[(calls["strike"] - stock_price).abs().argsort()[:1]].values[0] if not calls.empty else stock_price
                            put_strike = puts["strike"].iloc[(puts["strike"] - stock_price).abs().argsort()[:1]].values[0] if not puts.empty else stock_price
                            contracts = pd.concat([
                                calls[calls["strike"] == call_strike],
                                puts[puts["strike"] == put_strike]
                            ], ignore_index=True)
                            contracts["optionType"] = contracts["contractSymbol"].str[-9:].str[0].map({'C': 'calls', 'P': 'puts'})
                            logger.warning(f"[!] Fallback used for {ticker}, expiration {exp}: no common strikes, using call_strike={call_strike}, put_strike={put_strike}")
                    elif strike_spread:
                        atm_strike = stock_price
                        contracts = contracts[abs(contracts["strike"] - atm_strike) <= strike_spread]
                    elif multi_expirations and option_type == "calls":
                        # Use most liquid strike or nearest to ATM
                        if not df_list:
                            most_liquid_strike = contracts.loc[contracts["volume"].idxmax(), "strike"] if contracts["volume"].max() > 0 else stock_price
                        contracts = contracts[contracts["strike"] == most_liquid_strike]
                    # Apply minimal liquidity filter
                    contracts = contracts[(contracts["bid"] > 0) & (contracts["ask"] > 0)]
                    if not contracts.empty:
                        df_list.append(contracts)
                        logger.info(f"[i] Found {len(contracts)} valid contracts for {ticker}, expiration {exp}")
                if not multi_expirations:
                    break
        if df_list:
            df = pd.concat(df_list, ignore_index=True)
            logger.info(f"[i] Total {len(df)} rows for {ticker} after filtering")
            return df
        logger.warning(f"[!] No valid options data for {ticker} after filtering")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"[!] Failed to fetch options for {ticker}: {e}")
        return pd.DataFrame()

def fetch_all_options(output_dir=OPTIONS_RAW_DIR, min_days_out=0, max_days_out=1095, option_type="calls", symbols=None, strategy=None, force=False):
    """Fetch options data for a list of symbols."""
    output_dir = Path(output_dir) / (config["strategies"][strategy]["output_dir"] if strategy else "options")
    with open(TICKER_YAML, "r") as f:
        tickers = yaml.safe_load(f) or {}
    if symbols is None:
        categories = ["stocks", "etfs"]
        all_symbols = [sym for cat in categories for sym in tickers.get(cat, []) if not sym.endswith('-USD')]
    else:
        all_symbols = symbols

    output_dir.mkdir(parents=True, exist_ok=True)
    for symbol in all_symbols:
        output_path = output_dir / f"{symbol}.csv"
        if not force and not needs_update(output_path, "1d"):
            logger.info(f"[⏭] Skipping {symbol} ({strategy or 'options'}) – up-to-date")
            continue
        params = config["strategies"][strategy] if strategy else {}
        df = fetch_option_chain(
            symbol,
            min_days_out,
            max_days_out,
            option_type,
            multi_expirations=params.get("multi_expirations", False),
            same_strike=params.get("same_strike", False),
            strike_spread=params.get("strike_spread"),
            min_volume=params.get("min_volume", 0),
            min_open_interest=params.get("min_open_interest", 0)
        )
        if not df.empty:
            df = preprocess_options_data(df)
            df.to_csv(output_path, index=False)
            logger.info(f"[✓] Saved {option_type} for {symbol} ({strategy or 'options'}) → {output_path} ({len(df)} rows)")
            time.sleep(0.5)
        else:
            logger.info(f"[✗] No {option_type} saved for {symbol} ({strategy or 'options'})")

def load_tickers(category=None, yaml_file=TICKER_YAML):
    """Load tickers from YAML."""
    try:
        with open(yaml_file, "r") as f:
            data = yaml.safe_load(f) or {}
        if not data.get("stocks") and not data.get("etfs"):
            logger.error(f"[!] No stocks or ETFs found in {yaml_file}")
            return []
        if category:
            return [sym for sym in data.get(category, []) if not sym.endswith('-USD')]
        return [sym for cat in ["stocks", "etfs"] for sym in data.get(cat, []) if not sym.endswith('-USD')]
    except Exception as e:
        logger.error(f"[!] Failed to load {yaml_file}: {e}")
        return []

if __name__ == "__main__":
    for strategy, params in config["strategies"].items():
        fetch_all_options(
            min_days_out=params["min_dte"],
            max_days_out=params["max_dte"],
            option_type=params["option_type"],
            symbols=load_tickers(),
            strategy=strategy,
            force=False
        )