import click
import yaml
from pathlib import Path
from stonkslib.utils.logging import setup_logging
from stonkslib.analysis.signals import aggregate_and_save
from stonkslib.analysis.options.leaps_calls import analyze_leaps_calls
from stonkslib.analysis.options.leaps_puts import analyze_leaps_puts
from stonkslib.analysis.options.covered_calls import analyze_covered_calls
from stonkslib.analysis.options.secured_puts import analyze_secured_puts
from stonkslib.analysis.options.wheel import analyze_wheel

# Load configuration
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
TICKER_YAML = PROJECT_ROOT / "tickers.yaml"

# Setup logging
logger = setup_logging(PROJECT_ROOT / "log", "analyze.log")

# Load config.yaml with error handling
try:
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)
    if config is None:
        raise ValueError("config.yaml is empty or invalid")
except FileNotFoundError:
    logger.error(f"[!] Config file not found at {CONFIG_PATH}")
    config = {
        "project": {
            "ticker_data_dir": "data/ticker_data/clean",
            "options_data_dir": "data/options_data/clean",
            "analysis_dir": "data/analysis/signals",
            "log_dir": "log"
        },
        "strategies": {
            "leaps_calls": {"min_dte": 365, "max_dte": 730, "side": "buy", "type": "calls"},
            "leaps_puts": {"min_dte": 365, "max_dte": 730, "side": "buy", "type": "puts"},
            "covered_calls": {"min_dte": 21, "max_dte": 45, "side": "sell", "type": "calls"},
            "secured_puts": {"min_dte": 21, "max_dte": 45, "side": "sell", "type": "puts"},
            "wheel": {"min_dte": 21, "max_dte": 45, "side": "sell", "type": "both"}
        }
    }
except Exception as e:
    logger.error(f"[!] Error loading config.yaml: {e}")
    config = {
        "project": {
            "ticker_data_dir": "data/ticker_data/clean",
            "options_data_dir": "data/options_data/clean",
            "analysis_dir": "data/analysis/signals",
            "log_dir": "log"
        },
        "strategies": {}
    }

def load_tickers(yaml_file=TICKER_YAML):
    try:
        with open(yaml_file, "r") as f:
            data = yaml.safe_load(f)
        result = []
        for category in data:
            items = data[category]
            if isinstance(items, str):
                items = [items]
            result.extend(items)
        return result
    except Exception as e:
        logger.error(f"[!] Failed to load tickers.yaml: {e}")
        return []

@click.group()
def analyze():
    """Run signal analysis."""

@analyze.command()
@click.option("--ticker", type=str, default=None, help="Specific ticker to analyze (default: all from tickers.yaml)")
@click.option(
    "--interval",
    type=click.Choice(["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk"]),
    default="1d",
    help="Specific interval to analyze (default: 1d)"
)
def stocks(ticker, interval):
    """Analyze stock, ETF, and crypto OHLC data."""
    logger.info(f"Running analysis for stocks (ticker={ticker or 'all'}, interval={interval})...")
    tickers = [ticker] if ticker else load_tickers()
    results = []
    
    for t in tickers:
        try:
            status = aggregate_and_save(t, interval)  # From stonkslib/analysis/signals.py
            if status:
                logger.info(f"[✓] Analyzed {t} ({interval}): {status}")
                results.append({"ticker": t, "interval": interval, "status": status})
            else:
                logger.warning(f"[!] No signals for {t} ({interval})")
        except Exception as e:
            logger.error(f"[!] Failed to analyze {t} ({interval}): {e}")
    print(f"[✓] Stock analysis complete: {len(results)} tickers processed")
    return results

@analyze.command()
@click.option("--ticker", type=str, default=None, help="Specific ticker to analyze (default: all from tickers.yaml)")
@click.option(
    "--strategy",
    type=click.Choice(["leaps_calls", "leaps_puts", "covered_calls", "secured_puts", "wheel"]),
    default=None,
    help="Specific strategy to analyze (default: all from config.yaml)"
)
@click.option(
    "--side",
    type=click.Choice(["buy", "sell"]),
    default=None,
    help="Buy or sell side for options (default: from config.yaml)"
)
@click.option(
    "--option_type",
    type=click.Choice(["calls", "puts"]),
    default=None,
    help="Option type (calls or puts, default: from config.yaml)"
)
def options(ticker, strategy, side, option_type):
    """Analyze options data."""
    logger.info(f"Running analysis for options (ticker={ticker or 'all'}, strategy={strategy or 'all'}, side={side or 'all'}, option_type={option_type or 'all'})...")
    tickers = [ticker] if ticker else load_tickers()
    strategies = [strategy] if strategy else config.get("strategies", {}).keys()
    data_dir = PROJECT_ROOT / config["project"]["options_data_dir"]
    
    results = []
    for t in tickers:
        for s in strategies:
            if s not in config.get("strategies", {}):
                logger.error(f"[!] Strategy {s} not in config.yaml")
                continue
            strategy_config = config["strategies"][s]
            effective_side = side if side else strategy_config.get("side", "buy")
            effective_type = option_type if option_type else strategy_config.get("type", "calls")
            if effective_side not in ["buy", "sell"] or (s == "wheel" and effective_side != "sell"):
                logger.error(f"[!] Invalid side {effective_side} for strategy {s}")
                continue
            if effective_type not in ["calls", "puts", "both"]:
                logger.error(f"[!] Invalid option type {effective_type} for strategy {s}")
                continue
            try:
                csv_path = data_dir / (f"{s}/{effective_type}" if effective_type != "both" else s) / f"{t}.csv"
                if not csv_path.exists():
                    logger.warning(f"[!] Missing data for {t} ({s}, {effective_type})")
                    continue
                if s == "leaps_calls" and effective_side == "buy" and effective_type == "calls":
                    df = analyze_leaps_calls(t, s)
                elif s == "leaps_puts" and effective_side == "buy" and effective_type == "puts":
                    df = analyze_leaps_puts(t, s)
                elif s == "covered_calls" and effective_side == "sell" and effective_type == "calls":
                    df = analyze_covered_calls(t, s)
                elif s == "secured_puts" and effective_side == "sell" and effective_type == "puts":
                    df = analyze_secured_puts(t, s)
                elif s == "wheel" and effective_side == "sell":
                    df = analyze_wheel(t, s)
                else:
                    logger.warning(f"[!] Unsupported strategy {s} with side {effective_side} and type {effective_type}")
                    continue
                if df is not None:
                    logger.info(f"[✓] Analyzed {t} ({s}, {effective_side}, {effective_type}) — {len(df)} signals")
                    results.append({"ticker": t, "strategy": s, "side": effective_side, "option_type": effective_type, "signals": df.to_dict(orient="records")})
                else:
                    logger.warning(f"[!] No signals for {t} ({s}, {effective_side}, {effective_type})")
            except Exception as e:
                logger.error(f"[!] Failed to analyze {t} ({s}, {effective_side}, {effective_type}): {e}")
    print(f"[✓] Options analysis complete: {len(results)} tickers processed")
    return results

if __name__ == "__main__":
    analyze()